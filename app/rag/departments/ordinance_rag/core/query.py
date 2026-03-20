"""
ordinance_rag/core/query.py

Query pipeline for ordinance RAG.
Takes a user question + jurisdiction key, retrieves the most relevant
ordinance chunks, and generates a cited answer using the LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.rag.departments.ordinance_rag.core.store import get_collection, collection_exists
from app.rag.departments.ordinance_rag.core.scope_guard import is_in_scope, get_refusal_message

JURISDICTIONS_DIR = Path(__file__).resolve().parents[1] / "jurisdictions"
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

EMBED_MODEL = "nomic-embed-text"
ANSWER_MODEL = "llama3.2:3b"        # fast model for Q&A
TOP_K = 6                           # number of chunks to retrieve


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config(jurisdiction_key: str) -> dict:
    config_path = JURISDICTIONS_DIR / jurisdiction_key / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_system_prompt(jurisdiction_key: str, config: dict) -> str:
    """
    Build the full system prompt by combining:
    - base_template.txt
    - scope_guard.txt
    - jurisdiction's own system_prompt.txt
    All placeholders are filled from config.json.
    """
    base = (PROMPTS_DIR / "base_template.txt").read_text(encoding="utf-8")
    scope = (PROMPTS_DIR / "scope_guard.txt").read_text(encoding="utf-8")
    jurisdiction_specific = (
        JURISDICTIONS_DIR / jurisdiction_key / "system_prompt.txt"
    ).read_text(encoding="utf-8")

    display_name = config["display_name"]
    doc_list = ", ".join(config.get("documents", []))

    # Fill scope guard placeholder first
    scope = scope.replace("{jurisdiction_display_name}", display_name)

    # Fill base template
    full_prompt = base.replace("{jurisdiction_display_name}", display_name)
    full_prompt = full_prompt.replace("{scope_guard}", scope)
    full_prompt = full_prompt.replace("{document_list}", doc_list)

    # Append jurisdiction-specific context at the end
    full_prompt += f"\n\n{jurisdiction_specific}"

    return full_prompt


def _embed_query(question: str, ollama_client) -> list[float]:
    return ollama_client.embed(EMBED_MODEL, question)


def _retrieve(question_embedding: list[float], collection_name: str) -> list[dict]:
    """Retrieve top-K most relevant chunks from the jurisdiction's collection."""
    collection = get_collection(collection_name)
    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=TOP_K,
        include=["documents", "metadatas", "distances"],
    )
    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": doc,
            "source": meta.get("source", "unknown"),
            "chunk_index": meta.get("chunk_index", 0),
            "relevance_score": round(1 - dist, 4),
        })
    return chunks


def _build_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a readable context block for the LLM."""
    lines = []
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[Source {i}: {chunk['source']}]")
        lines.append(chunk["text"])
        lines.append("")
    return "\n".join(lines)


def _generate_answer(
    system_prompt: str,
    context: str,
    question: str,
    ollama_client,
) -> str:
    """Send context + question to the LLM and return the answer."""
    user_message = (
        f"Use the following ordinance excerpts to answer the question.\n\n"
        f"--- Ordinance Excerpts ---\n{context}\n"
        f"--- End of Excerpts ---\n\n"
        f"Question: {question}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return ollama_client.chat(model=ANSWER_MODEL, messages=messages)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def answer_question(
    jurisdiction_key: str,
    question: str,
    ollama_client,
) -> dict:
    """
    Full query pipeline for a jurisdiction.

    Args:
        jurisdiction_key:  e.g. "county", "wade", "falcon"
        question:          the user's question
        ollama_client:     OllamaClient instance

    Returns:
        dict with answer, citations, and jurisdiction info
    """
    config = _load_config(jurisdiction_key)
    display_name = config["display_name"]
    collection_name = config["collection_name"]

    # 1. Scope check — refuse immediately if off-topic
    if not is_in_scope(question):
        return {
            "answer": get_refusal_message(display_name),
            "citations": [],
            "jurisdiction": jurisdiction_key,
            "in_scope": False,
        }

    # 2. Check collection is indexed
    if not collection_exists(collection_name):
        return {
            "answer": (
                f"The {display_name} ordinance documents have not been indexed yet. "
                f"Please contact the Planning office or ask an administrator to run ingestion."
            ),
            "citations": [],
            "jurisdiction": jurisdiction_key,
            "in_scope": True,
        }

    # 3. Embed question
    question_embedding = _embed_query(question, ollama_client)

    # 4. Retrieve relevant chunks
    chunks = _retrieve(question_embedding, collection_name)

    # 5. Build context
    context = _build_context(chunks)

    # 6. Build system prompt
    system_prompt = _load_system_prompt(jurisdiction_key, config)

    # 7. Generate answer
    answer = _generate_answer(system_prompt, context, question, ollama_client)

    # 8. Build citations list
    citations = [
        {
            "source": c["source"],
            "chunk_index": c["chunk_index"],
            "relevance_score": c["relevance_score"],
        }
        for c in chunks
    ]

    return {
        "answer": answer,
        "citations": citations,
        "jurisdiction": jurisdiction_key,
        "display_name": display_name,
        "in_scope": True,
    }