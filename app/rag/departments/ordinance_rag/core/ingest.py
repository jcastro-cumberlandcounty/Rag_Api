"""
ordinance_rag/core/ingest.py

Ingestion pipeline for jurisdiction ordinance PDFs.
Reads all PDFs from a jurisdiction's docs/ folder,
chunks the text, generates embeddings, and stores in
that jurisdiction's isolated ChromaDB collection.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Generator

import time
import fitz  # PyMuPDF
from app.rag.departments.ordinance_rag.core.store import delete_collection, get_collection

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHUNK_SIZE = 800        # characters per chunk
CHUNK_OVERLAP = 150     # overlap between consecutive chunks
EMBED_MODEL = "nomic-embed-text"   # Ollama embedding model

JURISDICTIONS_DIR = Path(__file__).resolve().parents[1] / "jurisdictions"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config(jurisdiction_key: str) -> dict:
    """Load a jurisdiction's config.json."""
    config_path = JURISDICTIONS_DIR / jurisdiction_key / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"No config.json found for jurisdiction: {jurisdiction_key}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract all text from a PDF using PyMuPDF.
    Tries 'text' mode first, falls back to 'blocks' if that returns little content.
    """
    doc = fitz.open(str(pdf_path))
    pages = []
    for page in doc:
        # Primary extraction
        text = page.get_text("text")
        if not text.strip():
            # Fallback: extract from blocks (handles some encoding edge cases)
            blocks = page.get_text("blocks")
            text = "\n".join(b[4] for b in blocks if isinstance(b[4], str))
        if text.strip():
            pages.append(text)
    doc.close()
    return "\n".join(pages)


def _clean_text(text: str) -> str:
    """Basic cleanup — collapse excess whitespace, normalize line breaks."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _chunk_text(text: str, source: str) -> Generator[dict, None, None]:
    """
    Slide a window over text to produce overlapping chunks.
    Each chunk carries metadata: source filename and a stable chunk_id.
    """
    start = 0
    chunk_index = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunk_id = hashlib.md5(f"{source}:{chunk_index}".encode()).hexdigest()
            yield {
                "id": chunk_id,
                "text": chunk,
                "metadata": {
                    "source": source,
                    "chunk_index": chunk_index,
                },
            }
            chunk_index += 1
        start += CHUNK_SIZE - CHUNK_OVERLAP


def _embed_one(text: str, ollama_client, retries: int = 3) -> list[float] | None:
    """
    Embed a single text string with retry logic.
    Returns None if all retries fail.
    """
    for attempt in range(retries):
        try:
            vector = ollama_client.embed(EMBED_MODEL, text)
            if vector:
                return vector
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff
            else:
                raise e
    return None


def _embed(texts: list[str], ollama_client) -> list[list[float]]:
    """Generate embeddings for a list of text chunks via Ollama."""
    embeddings = []
    for text in texts:
        vector = _embed_one(text, ollama_client)
        embeddings.append(vector)
        time.sleep(0.1)  # Small delay to avoid overwhelming Ollama
    return embeddings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_jurisdiction(
    jurisdiction_key: str,
    ollama_client,
    force_reindex: bool = False,
) -> dict:
    """
    Ingest all PDFs for a jurisdiction into its ChromaDB collection.

    Args:
        jurisdiction_key:  folder name under jurisdictions/ (e.g. "county")
        ollama_client:     OllamaClient instance from app.rag.ollama_client
        force_reindex:     if True, wipe the collection and rebuild from scratch

    Returns:
        dict with status, chunks_added, and any errors per file
    """
    config = _load_config(jurisdiction_key)
    collection_name = config["collection_name"]
    docs_dir = JURISDICTIONS_DIR / jurisdiction_key / "docs"

    if not docs_dir.exists():
        return {"status": "error", "message": f"docs/ folder not found for {jurisdiction_key}"}

    pdf_files = list(docs_dir.glob("*.pdf"))
    if not pdf_files:
        return {"status": "error", "message": f"No PDFs found in {docs_dir}"}

    if force_reindex:
        delete_collection(collection_name)

    collection = get_collection(collection_name)

    total_chunks = 0
    file_results = []

    for pdf_path in pdf_files:
        try:
            raw_text = _extract_text_from_pdf(pdf_path)
            clean = _clean_text(raw_text)

            # Skip PDFs with no extractable text (truly scanned/image-based)
            if not clean or len(clean) < 30:
                file_results.append({
                    "file": pdf_path.name,
                    "status": "skipped",
                    "reason": "No extractable text — PDF may be scanned/image-based. Consider OCR.",
                })
                continue

            chunks = list(_chunk_text(clean, source=pdf_path.name))

            # Embed one at a time with retry — filter out any that fail
            valid_ids, valid_texts, valid_metadatas, valid_embeddings = [], [], [], []
            failed = 0
            for chunk in chunks:
                try:
                    vector = _embed_one(chunk["text"], ollama_client)
                    if vector:
                        valid_ids.append(chunk["id"])
                        valid_texts.append(chunk["text"])
                        valid_metadatas.append(chunk["metadata"])
                        valid_embeddings.append(vector)
                    else:
                        failed += 1
                except Exception:
                    failed += 1

            if not valid_embeddings:
                file_results.append({
                    "file": pdf_path.name,
                    "status": "error",
                    "error": "All chunks failed to embed.",
                })
                continue

            # Upsert only the valid chunks
            collection.upsert(
                ids=valid_ids,
                documents=valid_texts,
                embeddings=valid_embeddings,
                metadatas=valid_metadatas,
            )

            total_chunks += len(valid_embeddings)
            file_results.append({
                "file": pdf_path.name,
                "status": "ok",
                "chunks": len(valid_embeddings),
                "failed_chunks": failed,
            })

        except Exception as e:
            file_results.append({
                "file": pdf_path.name,
                "status": "error",
                "error": str(e),
            })

    return {
        "status": "ok",
        "jurisdiction": jurisdiction_key,
        "collection": collection_name,
        "total_chunks": total_chunks,
        "files": file_results,
    }