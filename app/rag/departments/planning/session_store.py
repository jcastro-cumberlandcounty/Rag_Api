"""
session_store.py   -  Plat Review Session Store
================================================
Manages persistent session data for the AI-powered plat review workflow.

Each session lives in a dedicated folder on the VM:
    data/sessions/{session_id}/
        session.json       - compliance report + extracted fields + observations
        plat.{ext}         - original uploaded plat image or PDF

The session_id is a UUID generated at the time of the /check-plat-image call.
It is returned to Blazor and stored in component state so that every subsequent
/chat-plat and /fill-checklist call can reload the full context.

Design notes
------------
- JSON-only storage for MVP.  Fields are structured for easy migration to a
  database later (all data in one dict under stable top-level keys).
- Image is stored as a raw binary file.  The chat endpoint re-reads it and
  re-encodes it as base64 for each vision call rather than storing base64 in
  JSON (keeps session.json smaller and avoids double-encoding issues).
- Directory creation uses exist_ok=True to survive restarts gracefully.
- All errors surface as plain Python exceptions; callers decide whether to
  translate them into HTTP 404/500.

Future DB migration path
------------------------
When moving to SQL Server:
  - session.json  ->  PlatReviewSession table (json column for report/fields)
  - plat.{ext}    ->  blob storage or a separate PlatImages table
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base directory for all sessions
# Can be overridden via PLAT_SESSION_DIR environment variable for flexibility
# ---------------------------------------------------------------------------
_DEFAULT_SESSION_DIR = Path("data/sessions")
SESSION_DIR = Path(os.environ.get("PLAT_SESSION_DIR", _DEFAULT_SESSION_DIR))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _session_dir(session_id: str) -> Path:
    """Return the directory path for a single session (does not create it)."""
    return SESSION_DIR / session_id


def _session_json_path(session_id: str) -> Path:
    return _session_dir(session_id) / "session.json"


def _plat_image_path(session_id: str, ext: str) -> Path:
    """Return the plat image path.  ext should include the dot, e.g. '.png'."""
    return _session_dir(session_id) / f"plat{ext}"


def _ensure_session_dir_exists(session_id: str) -> Path:
    """Create the session directory if it does not already exist."""
    d = _session_dir(session_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def new_session_id() -> str:
    """Generate a new unique session ID (UUID4 hex string)."""
    return str(uuid.uuid4())


def create_session(
    session_id: str,
    report: dict[str, Any],
    planner_observations: list[str],
    extracted_fields: dict[str, Any],
    image_bytes: bytes,
    image_ext: str,
    submission_type: str,
    jurisdiction: str,
    source_filename: str,
) -> Path:
    """
    Persist a new plat review session to disk.

    Parameters
    ----------
    session_id          : UUID string (from new_session_id())
    report              : full compliance report dict from build_report()
    planner_observations: list of narrative strings from Pass 2 vision
    extracted_fields    : raw dict of what the vision model extracted
    image_bytes         : raw bytes of the original uploaded file
    image_ext           : file extension including dot, e.g. '.png' or '.pdf'
    submission_type     : 'preliminary_plan' or 'final_plat'
    jurisdiction        : 'county' or 'wade'
    source_filename     : original filename from the upload

    Returns
    -------
    Path to the session directory.

    Raises
    ------
    PermissionError  if the data/sessions directory is not writable.
    OSError          for other filesystem problems.
    """
    _ensure_session_dir_exists(session_id)

    # ---- Save image --------------------------------------------------------
    ext = image_ext if image_ext.startswith(".") else f".{image_ext}"
    img_path = _plat_image_path(session_id, ext)
    img_path.write_bytes(image_bytes)
    logger.info("Session %s: saved plat image -> %s (%d bytes)",
                session_id, img_path, len(image_bytes))

    # ---- Save JSON ---------------------------------------------------------
    # Only store failures + warnings in the top-level report_summary to keep
    # the file lean; store the full report under report_full for reference.
    failures = report.get("failures", [])
    warnings = report.get("warnings", [])

    session_data: dict[str, Any] = {
        "session_id":           session_id,
        "submission_type":      submission_type,
        "jurisdiction":         jurisdiction,
        "source_filename":      source_filename,
        "plat_image_ext":       ext,
        "planner_observations": planner_observations,
        "extracted_fields":     extracted_fields,
        # Lean summary for chat prompt (failures + warnings only)
        "report_failures":      failures,
        "report_warnings":      warnings,
        "overall_status":       report.get("overall_status", "UNKNOWN"),
        "summary":              report.get("summary", {}),
        # Full report preserved for checklist fill and PDF export
        "report_full":          report,
    }

    json_path = _session_json_path(session_id)
    json_path.write_text(
        json.dumps(session_data, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Session %s: saved session.json -> %s", session_id, json_path)

    return _session_dir(session_id)


def load_session(session_id: str) -> dict[str, Any]:
    """
    Load a session from disk and return the full session dict.

    Raises
    ------
    FileNotFoundError  if the session does not exist.
    ValueError         if the JSON is malformed.
    """
    json_path = _session_json_path(session_id)
    if not json_path.exists():
        raise FileNotFoundError(f"Session not found: {session_id}")

    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corrupt session data for {session_id}: {exc}") from exc


def load_session_image(session_id: str) -> tuple[bytes, str]:
    """
    Load the plat image bytes for a session.

    Returns
    -------
    (image_bytes, ext)   - ext includes the leading dot, e.g. '.png'

    Raises
    ------
    FileNotFoundError  if the session or image does not exist.
    """
    session = load_session(session_id)
    ext = session.get("plat_image_ext", ".png")
    img_path = _plat_image_path(session_id, ext)

    if not img_path.exists():
        raise FileNotFoundError(
            f"Plat image not found for session {session_id}: {img_path}"
        )

    return img_path.read_bytes(), ext


def session_exists(session_id: str) -> bool:
    """Return True if a valid session exists on disk."""
    return _session_json_path(session_id).exists()


def check_permissions() -> dict[str, Any]:
    """
    Verify that the sessions directory is accessible and writable.
    Returns a status dict for the /health endpoint.

    Safe to call at startup to surface permission problems early.
    """
    result: dict[str, Any] = {
        "session_dir": str(SESSION_DIR),
        "exists":      SESSION_DIR.exists(),
        "writable":    False,
        "error":       None,
    }
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        test_file = SESSION_DIR / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        result["writable"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        logger.error("Sessions directory not writable: %s", exc)

    return result