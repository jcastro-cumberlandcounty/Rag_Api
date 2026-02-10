from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
import faiss

from .ollama_client import OllamaClient
from .pdf_extract import extract_pages
from .text_chunking import chunk_page_text
from .store import PolicyStore, StoredChunk


# -------------------------------
# Ingestion helpers
# -------------------------------

def build_chunks(
    policy_id: str,
    pages: Dict[int, str],
    max_chars: int = 1200,
    overlap_chars: int = 200,
) -> List[StoredChunk]:
    """
    Convert extracted pages into stable, stored chunks.
    """
    chunks: List[StoredChunk] = []

    for page_num in sorted(pages.keys()):
        page_chunks = chunk_page_text(
            page_num,
            pages[page_num],
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )

        for ch in page_chunks:
            chunk_id = PolicyStore.stable_chunk_id(
                policy_id,
                ch.page,
                ch.chunk_index,
                ch.text,
            )
            chunks.append(
                StoredChunk(
                    chunk_id=chunk_id,
                    page=ch.page,
                    chunk_index=ch.chunk_index,
                    text=ch.text,
                )
            )

    return chunks


def ingest_policy(
    store: PolicyStore,
    ollama: OllamaClient,
    policy_id: str,
    pdf_path: str,
    embedding_model: str,
    chunk_max_chars: int = 1200,
    chunk_overlap_chars: int = 200,
) -> Dict[str, Any]:
    """
    Full ingestion pipeline:
    PDF -> pages -> chunks -> embeddings -> FAISS index
    """

    # 1) Extract text by page
    pages = extract_pages(pdf_path)

    # 2) Build deterministic chunks
    chunks = build_chunks(
        policy_id,
        pages,
        max_chars=chunk_max_chars,
        overlap_chars=chunk_overlap_chars,
    )

    # 3) Create embeddings for each chunk
    vectors: List[List[float]] = []
    for chunk in chunks:
        vec = ollama.embed(embedding_model, chunk.text)
        vectors.append(vec)

    vectors_np = np.array(vectors, dtype=np.float32)

    # 4) Persist everything to disk
    store.write_pages(policy_id, pages)
    store.write_chunks(policy_id, chunks)
    store.write_faiss_index(policy_id, vectors_np)

    # 5) Save metadata for auditing
    meta = {
        "policy_id": policy_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "embedding_model": embedding_model,
        "chunk_max_chars": chunk_max_chars,
        "chunk_overlap_chars": chunk_overlap_chars,
        "pages": len(pages),
        "chunks": len(chunks),
    }

    store.write_meta(policy_id, meta)
    return meta


# -------------------------------
# Retrieval + answering
# -------------------------------

def retrieve_chunks(
    store: PolicyStore,
    ollama: OllamaClient,
    policy_id: str,
    question: str,
    embedding_model: str,
    top_k: int = 6,
) -> List[Tuple[float, StoredChunk]]:
    """
    Retrieve the most relevant chunks for a question.
    """

    # Load index and chunks
    index = store.load_faiss_index(policy_id)
    chunks = store.load_chunks(policy_id)

    # Embed the question
    q_vec = np.array(
        [ollama.embed(embedding_model, question)],
        dtype=np.float32,
    )

    # Normalize to match cosine-style similarity
    faiss.normalize_L2(q_vec)

    # Perform vector search
    scores, indices = index.search(q_vec, top_k)

    results: List[Tuple[float, StoredChunk]] = []
    for score, idx in zip(scores[0], indices[0]):
        if 0 <= idx < len(chunks):
            results.append((float(score), chunks[idx]))

    return results


def evidence_is_sufficient(
    retrieved: List[Tuple[float, StoredChunk]],
    min_score: float,
) -> bool:
    """
    Decide whether we have enough evidence to answer.
    """
    if not retrieved:
        return False

    best_score = max(score for score, _ in retrieved)
    return best_score >= min_score


def build_prompt(
    question: str,
    retrieved: List[Tuple[float, StoredChunk]],
) -> str:
    """
    Build a strict prompt that forbids guessing and requires citations.
    """

    excerpts = []
    for i, (score, chunk) in enumerate(retrieved, start=1):
        snippet = chunk.text[:700].strip()
        excerpts.append(
            f"[EXCERPT {i}] (page {chunk.page}, chunk {chunk.chunk_id}, score {score:.3f})\n"
            f"{snippet}\n"
        )

    joined_excerpts = "\n".join(excerpts)

    return f"""
You are a policy question-answering assistant.

RULES (must follow exactly):
- Use ONLY the policy excerpts provided.
- Do NOT use outside knowledge.
- Do NOT guess or infer.
- If the answer is not explicitly supported, respond exactly:
  I can’t find that in the policy excerpts provided.
- If you answer, cite each claim using: (p.<page>, excerpt <n>)

QUESTION:
{question}

POLICY EXCERPTS:
{joined_excerpts}

Answer now.
""".strip()


def answer_question(
    store: PolicyStore,
    ollama: OllamaClient,
    policy_id: str,
    question: str,
    embedding_model: str,
    chat_model: str,
    top_k: int,
    min_score: float,
) -> Dict[str, Any]:
    """
    End-to-end question answering with strict guardrails.
    """

    # 1) Retrieve relevant chunks
    retrieved = retrieve_chunks(
        store,
        ollama,
        policy_id,
        question,
        embedding_model,
        top_k=top_k,
    )

    # 2) Enforce "not found" if evidence is weak
    if not evidence_is_sufficient(retrieved, min_score):
        return {
            "answer": "I can’t find that in the policy excerpts provided.",
            "citations": [],
            "retrieved": [
                {
                    "score": score,
                    "page": chunk.page,
                    "chunk_id": chunk.chunk_id,
                    "preview": chunk.text[:200],
                }
                for score, chunk in retrieved
            ],
        }

    # 3) Build a grounded prompt
    prompt = build_prompt(question, retrieved)

    # 4) Ask the LLM
    response = ollama.generate(
        model=chat_model,
        prompt=prompt,
        temperature=0.0,
        top_p=1.0,
        seed=1,
    )

    # 5) Hard-enforce the rule in case the model slips
    if "I can’t find that in the policy excerpts provided." in response:
        return {
            "answer": "I can’t find that in the policy excerpts provided.",
            "citations": [],
            "retrieved": [],
        }

    # 6) Build citations for auditability
    citations = []
    for i, (score, chunk) in enumerate(retrieved, start=1):
        citations.append(
            {
                "excerpt": i,
                "page": chunk.page,
                "chunk_id": chunk.chunk_id,
                "score": score,
                "snippet": chunk.text[:220],
            }
        )

    return {
        "answer": response,
        "citations": citations,
        "retrieved": [
            {
                "score": score,
                "page": chunk.page,
                "chunk_id": chunk.chunk_id,
            }
            for score, chunk in retrieved
        ],
    }
