from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

from app.rag.ollama_client import OllamaClient
from app.rag.store import PolicyStore
from app.rag.rag_core import ingest_policy, answer_question

# Create the FastAPI app (this also powers /docs)
app = FastAPI(
    title="Policy RAG API",
    description="Closed-domain RAG service for policy documents (answers only from ingested PDFs)",
    version="0.1.0",
)

# Storage and Ollama clients are created once and reused (faster + simpler)
store = PolicyStore(root_dir="data/policies")
ollama = OllamaClient(base_url="http://localhost:11434")


class IngestResponse(BaseModel):
    policy_id: str
    pages: int
    chunks: int
    embedding_model: str


class AskRequest(BaseModel):
    policy_id: str = Field(..., description="Policy identifier to query")
    question: str = Field(..., description="User question")

    # Models are configurable per request
    embedding_model: str = Field(default="nomic-embed-text:latest")
    chat_model: str = Field(default="gpt-oss:20b")

    # Retrieval tuning knobs
    top_k: int = Field(default=6)
    min_score: float = Field(default=0.25)


@app.get("/health")
def health():
    # Lightweight health check (should not depend on PDFs or LLM)
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    pdf: UploadFile = File(...),
    policy_id: str | None = None,
    embedding_model: str = "nomic-embed-text:latest",
):
    """
    Upload and index a policy PDF.

    - Saves the PDF to data/policies/{policy_id}/source.pdf
    - Extracts pages
    - Chunks text
    - Embeds chunks
    - Writes FAISS index
    """

    # Basic content type check
    if pdf.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Upload must be a PDF")

    # If caller doesn't supply policy_id, generate one
    pid = policy_id or f"policy-{uuid.uuid4().hex[:10]}"

    # Read bytes and store PDF for provenance
    pdf_bytes = await pdf.read()
    pdf_path = store.write_pdf(pid, pdf_bytes)

    # Run ingestion pipeline
    try:
        meta = ingest_policy(
            store=store,
            ollama=ollama,
            policy_id=pid,
            pdf_path=str(pdf_path),
            embedding_model=embedding_model,
        )
    except Exception as e:
        # Keep the error message visible while we debug
        raise HTTPException(status_code=500, detail=str(e))

    return IngestResponse(
        policy_id=pid,
        pages=int(meta["pages"]),
        chunks=int(meta["chunks"]),
        embedding_model=meta["embedding_model"],
    )


@app.post("/ask")
def ask(req: AskRequest):
    """
    Ask a question against a specific ingested policy.

    Returns:
    - answer (strictly grounded)
    - citations (page + excerpt references)
    - retrieved chunk IDs (for auditing)
    """

    policy_dir = Path("data/policies") / req.policy_id
    if not policy_dir.exists():
        raise HTTPException(status_code=404, detail="Unknown policy_id (policy not ingested)")

    return answer_question(
        store=store,
        ollama=ollama,
        policy_id=req.policy_id,
        question=req.question,
        embedding_model=req.embedding_model,
        chat_model=req.chat_model,
        top_k=req.top_k,
        min_score=req.min_score,
    )
