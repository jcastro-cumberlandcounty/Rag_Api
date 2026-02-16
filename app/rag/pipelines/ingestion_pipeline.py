"""
Ingestion Pipeline Module

Purpose: Orchestrate the full document ingestion process (text + images)

This is the "conductor" that coordinates:
1. Text extraction and chunking (text_processor)
2. Image extraction and vision AI (vision_processor)
3. Embedding creation (Ollama)
4. Vector index building (FAISS)
5. Metadata and storage (PolicyStore)

Python concepts:
- Functions calling other functions (composition)
- Combining results from multiple sources
- Error handling with detailed logging
- Progress tracking for long operations
"""

from __future__ import annotations

from typing import List, Dict, Any
import numpy as np
import faiss

# Import our processors (the workers)
from app.rag.processors.text_processor import (
    extract_pdf_pages,
    chunk_pages,
    sanitize_text_for_embedding,
)
from app.rag.processors.vision_processor import create_image_chunks

# Import infrastructure
from app.rag.ollama_client import OllamaClient
from app.rag.store import PolicyStore
from app.rag.types import Chunk


# =============================================================================
# MAIN INGESTION PIPELINE
# =============================================================================

def ingest_policy_with_vision(
    store: PolicyStore,
    ollama: OllamaClient,
    policy_id: str,
    pdf_path: str,
    embedding_model: str,
    vision_model: str = "llama3.2-vision:11b",
    enable_vision: bool = True,
) -> Dict[str, Any]:
    """
    Complete ingestion pipeline: text + vision processing.
    
    This is the main orchestration function that ties everything together.
    It processes a PDF document and makes it searchable through RAG.
    
    Workflow:
    1. Extract text from all pages
    2. Chunk text into overlapping segments
    3. [OPTIONAL] Extract images and get AI descriptions
    4. Combine text chunks and image chunks
    5. Embed all chunks using embedding model
    6. Build FAISS vector search index
    7. Save everything to disk
    
    Args:
        store: PolicyStore for saving data
        ollama: OllamaClient for AI models
        policy_id: Unique identifier for this policy
        pdf_path: Path to the PDF file
        embedding_model: Model for creating embeddings (e.g., "nomic-embed-text:latest")
        vision_model: Model for image description (e.g., "llama3.2-vision:11b")
        enable_vision: Whether to process images (default True)
    
    Returns:
        Dictionary with ingestion results:
        {
            "policy_id": "policy-abc123",
            "pages": 25,
            "chunks": 80,
            "text_chunks": 65,
            "image_chunks": 15,
            "embedding_model": "nomic-embed-text:latest",
            "vision_model": "llama3.2-vision:11b",
            "chunks_failed": 2
        }
    """
    print(f"\n{'='*70}")
    print(f"INGESTION PIPELINE: {policy_id}")
    print(f"{'='*70}\n")
    
    # =========================================================================
    # STEP 1: Extract and chunk text
    # =========================================================================
    print("STEP 1: Extracting text from PDF...")
    pages = extract_pdf_pages(pdf_path)
    print(f"  ✓ Extracted {len(pages)} pages")
    
    print("STEP 2: Chunking text...")
    text_chunks = chunk_pages(pages)
    print(f"  ✓ Created {len(text_chunks)} text chunks")
    
    # =========================================================================
    # STEP 3: Extract and describe images (if enabled)
    # =========================================================================
    image_chunks: List[Chunk] = []
    
    if enable_vision:
        print("STEP 3: Processing images with vision AI...")
        try:
            image_chunks = create_image_chunks(
                ollama_client=ollama,
                pdf_path=pdf_path,
                vision_model=vision_model,
                min_image_size=10000,  # Skip tiny images
            )
            print(f"  ✓ Created {len(image_chunks)} image chunks")
        except Exception as e:
            print(f"  ⚠ Vision processing failed: {e}")
            print(f"  → Continuing with text-only ingestion")
    else:
        print("STEP 3: Vision processing DISABLED (enable_vision=False)")
    
    # =========================================================================
    # STEP 4: Combine all chunks
    # =========================================================================
    print("STEP 4: Combining text and image chunks...")
    all_chunks = text_chunks + image_chunks
    print(f"  ✓ Total chunks: {len(all_chunks)} ({len(text_chunks)} text + {len(image_chunks)} image)")
    
    # Handle case where we have no chunks at all
    if not all_chunks:
        # Write metadata about the failure
        store.write_metadata(
            policy_id,
            {
                "pages": len(pages),
                "chunks_total": 0,
                "chunks_embedded": 0,
                "chunks_failed": 0,
                "embedding_model": embedding_model,
                "vision_model": vision_model if enable_vision else None,
                "note": "No extractable text or images found (possibly scanned PDF).",
            },
        )
        return {
            "policy_id": policy_id,
            "pages": len(pages),
            "chunks": 0,
            "text_chunks": 0,
            "image_chunks": 0,
            "embedding_model": embedding_model,
        }
    
    # =========================================================================
    # STEP 5: Embed all chunks
    # =========================================================================
    print("STEP 5: Creating embeddings for all chunks...")
    
    vectors: List[List[float]] = []  # Will store the embedding vectors
    kept_chunks: List[Chunk] = []  # Chunks that embedded successfully
    failed_chunks: List[Dict[str, Any]] = []  # Chunks that failed
    
    policy_dir = store.policy_dir(policy_id)
    
    # Process each chunk one at a time
    for i, chunk in enumerate(all_chunks):
        # Show progress every 10 chunks
        if (i + 1) % 10 == 0:
            print(f"  Processing chunk {i+1}/{len(all_chunks)}...")
        
        # Clean the text before embedding
        safe_text = sanitize_text_for_embedding(chunk.text, max_chars=4000)
        
        # Skip if sanitization removed all content
        if not safe_text:
            failed_chunks.append({
                "page": chunk.page,
                "chunk_id": chunk.chunk_id,
                "error": "Empty after sanitization"
            })
            continue
        
        # Try to create embedding
        try:
            vec = ollama.embed(embedding_model, safe_text)
            vectors.append(vec)
            kept_chunks.append(chunk)
        
        except Exception as e:
            # If embedding fails, save the problematic text for debugging
            debug_path = policy_dir / f"FAILED_EMBED_{chunk.chunk_id}.txt"
            try:
                debug_path.write_text(safe_text, encoding="utf-8", errors="replace")
            except Exception:
                pass  # If we can't even save the debug file, just continue
            
            failed_chunks.append({
                "page": chunk.page,
                "chunk_id": chunk.chunk_id,
                "error": str(e)
            })
    
    print(f"  ✓ Successfully embedded {len(kept_chunks)}/{len(all_chunks)} chunks")
    
    if failed_chunks:
        print(f"  ⚠ {len(failed_chunks)} chunks failed (see metadata for details)")
    
    # If everything failed, we can't build an index
    if not vectors:
        store.write_metadata(
            policy_id,
            {
                "pages": len(pages),
                "chunks_total": len(all_chunks),
                "text_chunks": len(text_chunks),
                "image_chunks": len(image_chunks),
                "chunks_embedded": 0,
                "chunks_failed": len(failed_chunks),
                "embedding_model": embedding_model,
                "vision_model": vision_model if enable_vision else None,
                "failed_chunks_sample": failed_chunks[:25],
                "note": "All chunks failed embedding; see FAILED_EMBED_*.txt files.",
            },
        )
        raise RuntimeError(
            f"All chunks failed embedding for policy_id={policy_id}. "
            f"See data/policies/{policy_id}/FAILED_EMBED_*.txt for details."
        )
    
    # =========================================================================
    # STEP 6: Build FAISS vector index
    # =========================================================================
    print("STEP 6: Building FAISS search index...")
    
    # Convert list of vectors to numpy array (FAISS requires this)
    arr = np.array(vectors, dtype="float32")
    dim = arr.shape[1]  # Dimension of vectors (e.g., 768 for nomic-embed-text)
    
    # Normalize vectors for cosine similarity search
    # This makes the dot product equivalent to cosine similarity
    faiss.normalize_L2(arr)
    
    # Create FAISS index (IndexFlatIP = inner product, good for cosine similarity)
    index = faiss.IndexFlatIP(dim)
    index.add(arr)  # Add all vectors to the index
    
    print(f"  ✓ Index built with {index.ntotal} vectors (dimension: {dim})")
    
    # =========================================================================
    # STEP 7: Save everything to disk
    # =========================================================================
    print("STEP 7: Saving to disk...")
    
    # Save the FAISS index
    store.write_faiss_index(policy_id, index)
    print("  ✓ Saved FAISS index")
    
    # Save the chunks (for retrieval and citation)
    store.write_chunks(policy_id, kept_chunks)
    print("  ✓ Saved chunks")
    
    # Save metadata about the ingestion
    store.write_metadata(
        policy_id,
        {
            "pages": len(pages),
            "chunks_total": len(all_chunks),
            "text_chunks": len(text_chunks),
            "image_chunks": len(image_chunks),
            "chunks_embedded": len(kept_chunks),
            "chunks_failed": len(failed_chunks),
            "embedding_model": embedding_model,
            "vision_model": vision_model if enable_vision else None,
            "vector_dim": dim,
            "failed_chunks_sample": failed_chunks[:25],  # Save first 25 failures
        },
    )
    print("  ✓ Saved metadata")
    
    # =========================================================================
    # DONE!
    # =========================================================================
    print(f"\n{'='*70}")
    print(f"INGESTION COMPLETE: {policy_id}")
    print(f"  Text chunks: {len(text_chunks)}")
    print(f"  Image chunks: {len(image_chunks)}")
    print(f"  Total embedded: {len(kept_chunks)}")
    print(f"  Failed: {len(failed_chunks)}")
    print(f"{'='*70}\n")
    
    return {
        "policy_id": policy_id,
        "pages": len(pages),
        "chunks": len(kept_chunks),
        "text_chunks": len(text_chunks),
        "image_chunks": len(image_chunks),
        "embedding_model": embedding_model,
        "vision_model": vision_model if enable_vision else None,
        "chunks_failed": len(failed_chunks),
    }
