from __future__ import annotations

from typing import List, Dict, Any

import fitz  # PyMuPDF
import faiss
import numpy as np

from app.rag.ollama_client import OllamaClient
from app.rag.store import PolicyStore
from app.rag.types import Page, Chunk


# -------------------------
# Helpers
# -------------------------

def sanitize_text_for_embedding(text: str, max_chars: int = 4000) -> str:
    """
    Make PDF-extracted text safe for embedding calls.

    Deterministic steps:
    - Remove NUL bytes
    - Remove other control chars (keep newline/tab)
    - Normalize whitespace
    - Cap size
    """
    if not text:
        return ""

    safe = text.replace("\x00", " ")

    # Replace control chars (ASCII < 32) except \n and \t
    safe = "".join(
        ch if (ch == "\n" or ch == "\t" or ord(ch) >= 32) else " "
        for ch in safe
    )

    # Normalize whitespace
    safe = " ".join(safe.split())

    # Hard cap
    if len(safe) > max_chars:
        safe = safe[:max_chars]

    return safe.strip()


# -------------------------
# PDF extraction
# -------------------------

def extract_pdf_pages(pdf_path: str) -> List[Page]:
    """Read a PDF and return a list of pages with extracted text."""
    doc = fitz.open(pdf_path)
    pages: List[Page] = []

    for i, page in enumerate(doc):
        text = page.get_text() or ""
        pages.append(Page(page_num=i + 1, text=text))

    return pages


# -------------------------
# Chunking logic
# -------------------------

def chunk_pages(
    pages: List[Page],
    chunk_size: int = 900,
    overlap: int = 150,
) -> List[Chunk]:
    """Split pages into overlapping character chunks."""
    chunks: List[Chunk] = []

    for page in pages:
        text = page.text or ""
        start = 0
        chunk_idx = 0

        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(
                    Chunk(
                        chunk_id=f"p{page.page_num}_c{chunk_idx}",
                        page=page.page_num,
                        text=chunk_text,
                    )
                )

            start = end - overlap
            chunk_idx += 1

    return chunks


# -------------------------
# Ingestion pipeline
# -------------------------

def ingest_policy(
    store: PolicyStore,
    ollama: OllamaClient,
    policy_id: str,
    pdf_path: str,
    embedding_model: str,
) -> Dict[str, Any]:
    """
    Ingest a policy PDF:
    - extract pages
    - chunk text
    - embed chunks
    - build + persist FAISS index
    - write chunk metadata

    Resilient ingest: skips bad chunks but records them.
    """
    pages = extract_pdf_pages(pdf_path)
    chunks = chunk_pages(pages)

    if not chunks:
        store.write_metadata(
            policy_id,
            {
                "pages": len(pages),
                "chunks_total": 0,
                "chunks_embedded": 0,
                "chunks_failed": 0,
                "embedding_model": embedding_model,
                "note": "No extractable text found (possibly scanned PDF).",
            },
        )
        return {"policy_id": policy_id, "pages": len(pages), "chunks": 0, "embedding_model": embedding_model}

    vectors: List[List[float]] = []
    kept_chunks: List[Chunk] = []
    failed_chunks: List[Dict[str, Any]] = []

    policy_dir = store.policy_dir(policy_id)

    for ch in chunks:
        safe_text = sanitize_text_for_embedding(ch.text, max_chars=4000)

        if not safe_text:
            failed_chunks.append({"page": ch.page, "chunk_id": ch.chunk_id, "error": "Empty after sanitization"})
            continue

        try:
            vec = ollama.embed(embedding_model, safe_text)
        except Exception as e:
            # Dump failing text for inspection
            debug_path = policy_dir / f"FAILED_EMBED_{ch.chunk_id}.txt"
            try:
                debug_path.write_text(safe_text, encoding="utf-8", errors="replace")
            except Exception:
                pass

            failed_chunks.append({"page": ch.page, "chunk_id": ch.chunk_id, "error": str(e)})
            continue

        vectors.append(vec)
        kept_chunks.append(ch)

    if not vectors:
        store.write_metadata(
            policy_id,
            {
                "pages": len(pages),
                "chunks_total": len(chunks),
                "chunks_embedded": 0,
                "chunks_failed": len(failed_chunks),
                "embedding_model": embedding_model,
                "failed_chunks_sample": failed_chunks[:25],
                "note": "All chunks failed embedding; see FAILED_EMBED_*.txt files.",
            },
        )
        raise RuntimeError(
            f"All chunks failed embedding for policy_id={policy_id}. "
            f"See data/policies/{policy_id}/FAILED_EMBED_*.txt for details."
        )

    # Build FAISS index (cosine-ish via normalized inner product)
    arr = np.array(vectors, dtype="float32")
    dim = arr.shape[1]

    faiss.normalize_L2(arr)
    index = faiss.IndexFlatIP(dim)
    index.add(arr)

    store.write_faiss_index(policy_id, index)
    store.write_chunks(policy_id, kept_chunks)
    store.write_metadata(
        policy_id,
        {
            "pages": len(pages),
            "chunks_total": len(chunks),
            "chunks_embedded": len(kept_chunks),
            "chunks_failed": len(failed_chunks),
            "embedding_model": embedding_model,
            "vector_dim": dim,
            "failed_chunks_sample": failed_chunks[:25],
        },
    )

    return {
        "policy_id": policy_id,
        "pages": len(pages),
        "chunks": len(kept_chunks),
        "embedding_model": embedding_model,
        "chunks_failed": len(failed_chunks),
    }


# -------------------------
# Answer pipeline
# -------------------------

def answer_question(
    store: PolicyStore,
    ollama: OllamaClient,
    policy_id: str,
    question: str,
    embedding_model: str,
    chat_model: str,
    top_k: int = 6,
    min_score: float = 0.25,
) -> Dict[str, Any]:
    """Retrieve relevant chunks, then answer using ONLY those chunks with citations."""
    index = store.read_faiss_index(policy_id)
    chunks = store.read_chunks(policy_id)

    q_text = sanitize_text_for_embedding(question, max_chars=2000)
    qvec = np.array([ollama.embed(embedding_model, q_text)], dtype="float32")
    faiss.normalize_L2(qvec)

    scores, idxs = index.search(qvec, top_k)

    retrieved = []
    for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
        if idx < 0:
            continue
        if score < min_score:
            continue

        ch = chunks[idx]
        excerpt = sanitize_text_for_embedding(ch.text, max_chars=300).replace("\n", " ").strip()

        retrieved.append(
            {
                "chunk_id": ch.chunk_id,
                "page": ch.page,
                "score": float(score),
                "excerpt": excerpt,
                "text": ch.text,
            }
        )

    if not retrieved:
        return {
            "answer": "I can’t find that in the policy excerpts provided.",
            "citations": [],
            "retrieved_chunk_ids": [],
        }

    context_blocks = []
    for r in retrieved:
        context_blocks.append(f"[Page {r['page']} | {r['chunk_id']}]\n{r['text']}")

    system = (
        "You are a compliance assistant for government HR/policy documents.\n"
        "You MUST answer using ONLY the provided excerpts.\n"
        "If the answer is not explicitly supported by the excerpts, say:\n"
        "“I can’t find that in the policy excerpts provided.”\n"
        "Every factual claim must include a citation in the form (Page X, chunk_id).\n"
    )

    user = (
        "Policy excerpts:\n\n"
        + "\n\n---\n\n".join(context_blocks)
        + "\n\nQuestion:\n"
        + question
        + "\n\nAnswer using only excerpts and cite every claim."
    )

    answer_text = ollama.chat(
        chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    return {
        "answer": answer_text,
        "citations": [{"page": r["page"], "chunk_id": r["chunk_id"], "excerpt": r["excerpt"]} for r in retrieved],
        "retrieved_chunk_ids": [r["chunk_id"] for r in retrieved],
    }
