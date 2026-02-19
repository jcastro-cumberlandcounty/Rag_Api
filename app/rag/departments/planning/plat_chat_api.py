"""
plat_chat_api.py   -  /chat-plat  FastAPI Router
=================================================
Provides the AI chat endpoint for the plat review workflow.

Endpoint
--------
POST /chat-plat
    Accepts a session_id, a user message, and the full conversation history.
    Loads the session (compliance report failures/warnings + planner
    observations + extracted fields + plat image) from disk.
    Builds a lean system prompt from failures and warnings ONLY
    (to keep context window efficient).
    Always includes the plat image in every chat turn so the model
    can answer visual questions without re-upload.
    Calls gpt-oss:20b via the shared OllamaClient.
    Returns the AI reply and the updated conversation history.

Design decisions
----------------
- Image always included (simpler, avoids "I can't see that" failures,
  marginal speed cost vs reliability gain).
- System prompt uses failures + warnings only  -- not all 89 rules.
- History is managed client-side; backend is stateless per call.
  Each request must include the full conversation so far.
- Timeout handling: the OllamaClient call can take 60-120s for long
  context. Blazor should set its HttpClient.Timeout accordingly
  (recommend 120s) and show a spinner while waiting.

Content type determination
--------------------------
For images we send base64 with the correct MIME type.
For PDFs we convert page 1 to a base64 PNG via pdf2image before
sending to the vision model (same approach as plat_vision_extractor.py).
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .ollama_client import OllamaClient
from .session_store import load_session, load_session_image, session_exists

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat-plat", tags=["Planning - Plat Chat"])

# ---------------------------------------------------------------------------
# Models accepted and returned by the endpoint
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Session UUID from /check-plat-image")
    message: str    = Field(..., description="Planner's current question")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Full conversation so far (excluding the new message)",
    )


class ChatResponse(BaseModel):
    reply: str
    history: list[ChatMessage]
    session_id: str


# ---------------------------------------------------------------------------
# Dependency injection  - reuse the app-level OllamaClient
# ---------------------------------------------------------------------------

def get_ollama(request) -> OllamaClient:  # type: ignore[type-arg]
    return request.app.state.ollama


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
You are an expert land-use planner and NC-licensed surveyor assistant \
reviewing a plat submission for Cumberland County, NC.

You have access to:
1. The plat image (attached to this conversation).
2. A compliance report showing failures and warnings from the rule engine.
3. Planner observations generated during the initial AI review.

Your job is to help the reviewing planner understand specific issues, \
suggest concrete fixes, and cite the relevant ordinance section for each \
point.  Be direct and specific  -- reference lot numbers, measurements, \
and section numbers whenever possible.

--- COMPLIANCE FAILURES ---
{failures}

--- COMPLIANCE WARNINGS ---
{warnings}

--- PLANNER OBSERVATIONS ---
{observations}

--- EXTRACTED SUBMISSION DATA ---
{extracted_fields}

When answering questions:
- Quote the relevant ordinance section (e.g. "Sec. 2303 S.B") with every fix.
- If the question is about something you can see on the plat image, \
  describe the specific location (e.g. "Lot 7 in the northwest corner").
- If information is missing or unclear, say so rather than guessing.
- Keep answers focused and actionable.
"""


def _build_system_prompt(session: dict[str, Any]) -> str:
    """Build a lean system prompt from session data (failures + warnings only)."""

    def _fmt_rules(rule_list: list[dict]) -> str:
        if not rule_list:
            return "  None."
        lines = []
        for r in rule_list:
            rid   = r.get("rule_id", "")
            name  = r.get("rule_name", "")
            sec   = r.get("section", "")
            detail = r.get("detail", "")
            fix   = r.get("fix_suggestion", "")
            line = f"  [{rid}] {name}"
            if sec:
                line += f"  (Section {sec})"
            if detail:
                line += f"\n    Issue: {detail}"
            if fix:
                line += f"\n    Fix: {fix}"
            lines.append(line)
        return "\n".join(lines)

    failures    = _fmt_rules(session.get("report_failures", []))
    warnings    = _fmt_rules(session.get("report_warnings", []))
    observations = "\n".join(
        f"  - {obs}" for obs in session.get("planner_observations", [])
    ) or "  None."

    # Trim extracted fields to key values only (avoid blowing up context)
    raw_fields = session.get("extracted_fields", {})
    key_fields = {
        k: v for k, v in raw_fields.items()
        if v is not None and k not in (
            "raw_text", "vision_model", "extraction_prompt"
        )
    }
    extracted_str = json.dumps(key_fields, indent=2, default=str)

    return _SYSTEM_TEMPLATE.format(
        failures=failures,
        warnings=warnings,
        observations=observations,
        extracted_fields=extracted_str,
    )


# ---------------------------------------------------------------------------
# Image encoding helpers
# ---------------------------------------------------------------------------

def _ext_to_mime(ext: str) -> str:
    """Map a file extension to an Ollama-compatible MIME type."""
    mapping = {
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif":  "image/tiff",
        ".bmp":  "image/bmp",
        ".webp": "image/webp",
        ".pdf":  "image/png",   # PDFs get converted to PNG before this point
    }
    return mapping.get(ext.lower(), "image/png")


def _image_bytes_to_base64(image_bytes: bytes, ext: str) -> tuple[str, str]:
    """
    Return (base64_string, mime_type).
    PDFs are converted to a PNG of the first page before encoding.
    """
    if ext.lower() == ".pdf":
        try:
            from pdf2image import convert_from_bytes  # type: ignore
            pages = convert_from_bytes(image_bytes, first_page=1, last_page=1, dpi=150)
            import io
            buf = io.BytesIO()
            pages[0].save(buf, format="PNG")
            image_bytes = buf.getvalue()
            ext = ".png"
        except Exception as exc:
            logger.warning("PDF->PNG conversion failed, sending raw: %s", exc)

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime = _ext_to_mime(ext)
    return b64, mime


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ChatResponse,
    summary="Chat with AI about a plat review session",
    response_description="AI reply and updated conversation history.",
)
async def chat_plat(
    body: ChatRequest,
    request,  # FastAPI Request for app.state access
) -> ChatResponse:
    """
    Ask a natural-language question about a plat review session.

    The AI has the compliance report (failures + warnings), planner
    observations, extracted submission data, and the original plat image
    in context for every turn.

    Send the full conversation history with every request  -- the backend
    is stateless per call (history lives in the Blazor component).

    **Recommended Blazor HttpClient timeout**: 120 seconds.
    """
    ollama: OllamaClient = get_ollama(request)

    # ---- Validate session --------------------------------------------------
    if not session_exists(body.session_id):
        raise HTTPException(
            status_code=404,
            detail=f"Session not found: {body.session_id}",
        )

    # ---- Load session data -------------------------------------------------
    try:
        session = load_session(body.session_id)
    except Exception as exc:
        logger.exception("Failed to load session %s", body.session_id)
        raise HTTPException(status_code=500, detail=f"Failed to load session: {exc}") from exc

    # ---- Load image --------------------------------------------------------
    try:
        image_bytes, image_ext = load_session_image(body.session_id)
        b64_image, mime_type   = _image_bytes_to_base64(image_bytes, image_ext)
    except FileNotFoundError:
        b64_image  = None
        mime_type  = None
        logger.warning("Session %s: plat image not found  - chat will proceed without image.", body.session_id)
    except Exception as exc:
        logger.exception("Failed to load image for session %s", body.session_id)
        b64_image = None
        mime_type = None

    # ---- Build system prompt -----------------------------------------------
    system_prompt = _build_system_prompt(session)

    # ---- Build message list for Ollama -------------------------------------
    # Format: system (injected as first user turn for Ollama compatibility)
    # then alternating user/assistant from history, then the new user message
    # with the image attached.
    messages: list[dict[str, Any]] = []

    # System context as first message (Ollama /api/chat style)
    messages.append({
        "role":    "system",
        "content": system_prompt,
    })

    # Conversation history (text only for prior turns)
    for turn in body.history:
        messages.append({
            "role":    turn.role,
            "content": turn.content,
        })

    # New user message  -- include image
    if b64_image:
        new_user_message: dict[str, Any] = {
            "role": "user",
            "content": body.message,
            "images": [b64_image],
        }
    else:
        new_user_message = {
            "role":    "user",
            "content": body.message,
        }
    messages.append(new_user_message)

    # ---- Call the model ----------------------------------------------------
    # Use gpt-oss:20b (same model as RAG chat, multimodal-capable via Ollama)
    chat_model = "gpt-oss:20b"
    logger.info(
        "Session %s: /chat-plat turn %d  -- model=%s image=%s",
        body.session_id,
        len(body.history) + 1,
        chat_model,
        "yes" if b64_image else "no",
    )

    try:
        response = ollama.chat(
            model=chat_model,
            messages=messages,
            stream=False,
        )
    except Exception as exc:
        logger.exception("Ollama chat call failed for session %s", body.session_id)
        raise HTTPException(
            status_code=502,
            detail=f"AI model call failed: {exc}",
        ) from exc

    # ---- Extract reply text ------------------------------------------------
    reply_text: str = ""
    if isinstance(response, dict):
        # Ollama /api/chat returns {"message": {"role": "assistant", "content": "..."}}
        reply_text = (
            response.get("message", {}).get("content", "")
            or response.get("content", "")
            or str(response)
        )
    elif isinstance(response, str):
        reply_text = response
    else:
        reply_text = str(response)

    reply_text = reply_text.strip()
    if not reply_text:
        reply_text = "I was unable to generate a response. Please try again."

    # ---- Build updated history (text only  -- no image in stored history) ----
    updated_history = list(body.history) + [
        ChatMessage(role="user",      content=body.message),
        ChatMessage(role="assistant", content=reply_text),
    ]

    logger.info(
        "Session %s: /chat-plat reply generated (%d chars)",
        body.session_id,
        len(reply_text),
    )

    return ChatResponse(
        reply=reply_text,
        history=updated_history,
        session_id=body.session_id,
    )