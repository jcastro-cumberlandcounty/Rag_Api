"""
Query Pipeline Module

Purpose: Orchestrate question answering with RAG (Retrieval Augmented Generation)

This pipeline:
1. Takes a user's question
2. Embeds the question into a vector
3. Searches the FAISS index for relevant chunks (text + image descriptions)
4. Passes relevant chunks to the LLM
5. Gets back an answer with citations

Python concepts:
- Working with embeddings and vector search
- Building context from multiple sources
- Prompt engineering (telling the LLM how to behave)
"""

from __future__ import annotations

from typing import Dict, Any, List
import numpy as np
import faiss

from app.rag.ollama_client import OllamaClient
from app.rag.store import PolicyStore
from app.rag.processors.text_processor import sanitize_text_for_embedding


# =============================================================================
# QUERY PIPELINE
# =============================================================================

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
    """
    Answer a question using RAG (Retrieval Augmented Generation).
    
    How RAG works:
    1. We don't send the entire document to the LLM (too large, too expensive)
    2. Instead, we find the most relevant chunks using vector similarity
    3. We send only those relevant chunks as context
    4. The LLM answers based ONLY on those chunks
    5. We include citations so the user can verify the answer
    
    Args:
        store: PolicyStore to load chunks and index
        ollama: OllamaClient for embeddings and chat
        policy_id: Which policy to query
        question: User's question
        embedding_model: Model to embed the question
        chat_model: Model to generate the answer
        top_k: How many chunks to retrieve (default 6)
        min_score: Minimum similarity score to include a chunk (default 0.25)
    
    Returns:
        Dictionary with:
        {
            "answer": "The answer text...",
            "citations": [
                {"page": 5, "chunk_id": "p5_c2", "excerpt": "..."},
                {"page": 8, "chunk_id": "p8_img0", "excerpt": "..."}
            ],
            "retrieved_chunk_ids": ["p5_c2", "p8_img0", ...]
        }
    
    Example:
        result = answer_question(
            store, ollama, "policy-abc", "What is the remote work policy?", 
            "nomic-embed-text:latest", "gpt-oss:20b"
        )
        print(result["answer"])
        # "According to page 12, employees may work remotely up to 3 days per week..."
    """
    print(f"\n{'='*70}")
    print(f"QUERY PIPELINE: {policy_id}")
    print(f"Question: {question}")
    print(f"{'='*70}\n")
    
    # =========================================================================
    # STEP 1: Load the FAISS index and chunks
    # =========================================================================
    print("STEP 1: Loading policy data...")
    index = store.read_faiss_index(policy_id)
    chunks = store.read_chunks(policy_id)
    print(f"  ✓ Loaded index with {index.ntotal} vectors")
    print(f"  ✓ Loaded {len(chunks)} chunks")
    
    # =========================================================================
    # STEP 2: Embed the question
    # =========================================================================
    print("STEP 2: Embedding question...")
    q_text = sanitize_text_for_embedding(question, max_chars=2000)
    
    # Get embedding vector for the question
    qvec = np.array([ollama.embed(embedding_model, q_text)], dtype="float32")
    
    # Normalize for cosine similarity
    faiss.normalize_L2(qvec)
    print(f"  ✓ Question embedded (dimension: {qvec.shape[1]})")
    
    # =========================================================================
    # STEP 3: Search for relevant chunks
    # =========================================================================
    print(f"STEP 3: Searching for top {top_k} most relevant chunks...")
    
    # Search the index
    # scores = similarity scores (higher = more similar)
    # idxs = indices of the chunks in our chunks list
    scores, idxs = index.search(qvec, top_k)
    
    # Build list of retrieved chunks with their scores
    retrieved = []
    
    # Loop through results (scores and indices come as 2D arrays, so we use [0])
    for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
        # idx=-1 means "no result" (happens if we ask for more chunks than exist)
        if idx < 0:
            continue
        
        # Filter out low-quality matches
        if score < min_score:
            continue
        
        # Get the chunk data
        chunk = chunks[idx]
        
        # Create excerpt for citation (first 300 chars, one line)
        excerpt = sanitize_text_for_embedding(chunk.text, max_chars=300)
        excerpt = excerpt.replace("\n", " ").strip()
        
        retrieved.append({
            "chunk_id": chunk.chunk_id,
            "page": chunk.page,
            "score": float(score),  # Convert numpy float to Python float
            "excerpt": excerpt,
            "text": chunk.text,  # Full text for context
        })
    
    print(f"  ✓ Found {len(retrieved)} relevant chunks (score >= {min_score})")
    
    # If no relevant chunks found, return early
    if not retrieved:
        print("  ⚠ No relevant chunks found - cannot answer")
        return {
            "answer": "I can't find that information in the policy excerpts provided.",
            "citations": [],
            "retrieved_chunk_ids": [],
        }
    
    # =========================================================================
    # STEP 4: Build context for the LLM
    # =========================================================================
    print("STEP 4: Building context for LLM...")
    
    # Create numbered context blocks (makes it clear which chunk is which)
    context_blocks = []
    for r in retrieved:
        # Check if this is an image chunk (chunk_id contains "img")
        chunk_type = "IMAGE" if "_img" in r["chunk_id"] else "TEXT"
        
        context_blocks.append(
            f"[{chunk_type} | Page {r['page']} | {r['chunk_id']}]\n{r['text']}"
        )
    
    print(f"  ✓ Built context from {len(context_blocks)} chunks")
    
    # =========================================================================
    # STEP 5: Create prompt for the LLM
    # =========================================================================
    # This is "prompt engineering" - carefully instructing the LLM
    
    system = (
        "You are a compliance assistant for government HR/policy documents.\n"
        "You MUST answer using ONLY the provided excerpts.\n"
        "If the answer is not explicitly supported by the excerpts, say:\n"
        "\"I can't find that in the policy excerpts provided.\"\n"
        "\n"
        "IMPORTANT:\n"
        "- Excerpts marked [IMAGE ...] are AI descriptions of images/diagrams\n"
        "- When citing images, say \"According to the image on page X\" or \"The diagram on page X shows\"\n"
        "- Every factual claim must include a citation: (Page X, chunk_id)\n"
    )
    
    user = (
        "Policy excerpts:\n\n"
        + "\n\n---\n\n".join(context_blocks)
        + "\n\nQuestion:\n"
        + question
        + "\n\nAnswer using only the excerpts above and cite every claim."
    )
    
    # =========================================================================
    # STEP 6: Get answer from LLM
    # =========================================================================
    print("STEP 6: Generating answer with LLM...")
    
    answer_text = ollama.chat(
        chat_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    
    print(f"  ✓ Answer generated ({len(answer_text)} characters)")
    
    # =========================================================================
    # STEP 7: Format response with citations
    # =========================================================================
    print("STEP 7: Formatting response...")
    
    # Build citations list for the UI
    citations = [
        {
            "page": r["page"],
            "chunk_id": r["chunk_id"],
            "excerpt": r["excerpt"],
        }
        for r in retrieved
    ]
    
    # Get just the chunk IDs for debugging
    retrieved_chunk_ids = [r["chunk_id"] for r in retrieved]
    
    print(f"\n{'='*70}")
    print(f"QUERY COMPLETE")
    print(f"  Retrieved chunks: {len(retrieved)}")
    print(f"  Answer length: {len(answer_text)} chars")
    print(f"{'='*70}\n")
    
    return {
        "answer": answer_text,
        "citations": citations,
        "retrieved_chunk_ids": retrieved_chunk_ids,
    }
