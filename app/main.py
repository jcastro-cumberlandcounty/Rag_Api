"""
FastAPI Main Application

This is the web API that exposes RAG functionality via HTTP endpoints.

New architecture:
- Uses pipelines (ingestion_pipeline, query_pipeline) for orchestration
- Pipelines use processors (text_processor, vision_processor) for actual work
- Clean separation of concerns makes code easier to maintain and test

Endpoints:
- POST /ingest - Upload and index a PDF (with optional vision processing)
- POST /ask - Ask questions about an ingested policy
- GET /list-policies - List all ingested policies + Stand Allone Images
- GET /health - Health check
"""

from __future__ import annotations

import uuid
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import infrastructure
from app.rag.ollama_client import OllamaClient
from app.rag.store import PolicyStore

# Import our NEW pipeline orchestrators
from app.rag.pipelines.ingestion_pipeline import ingest_policy_with_vision
from app.rag.pipelines.query_pipeline import answer_question

# Import Planning
from rag.departments.planning.compliance_api import router as planning_router


# =============================================================================
# FastAPI App Setup
# =============================================================================

app = FastAPI(
    title="Policy RAG API with Vision",
    description=(
        "RAG service for policy documents with text + image processing. "
        "Uses vision AI to make diagrams, charts, and images searchable."
    ),
    version="0.3.0",  # Bumped version for new vision capabilities
)

# CORS middleware (allows web UIs to call this API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific domains
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the planning compliance router
app.include_router(planning_router)


# =============================================================================
# Initialize Storage and Clients (created once when server starts)
# =============================================================================

store = PolicyStore(root_dir="data/policies")
ollama = OllamaClient(base_url="http://localhost:11434")


# =============================================================================
# Response Models (define the shape of API responses)
# =============================================================================

class IngestResponse(BaseModel):
    """Response when a document is successfully ingested."""
    policy_id: str
    pages: int
    chunks: int
    text_chunks: int  # NEW: Separate count for text chunks
    image_chunks: int  # NEW: Separate count for image chunks
    embedding_model: str
    vision_model: str | None  # NEW: Which vision model was used (or None)


class AskRequest(BaseModel):
    """Request model for asking questions."""
    policy_id: str = Field(..., description="Policy identifier to query")
    question: str = Field(..., description="User question")

    # Model configuration
    embedding_model: str = Field(default="nomic-embed-text:latest")
    chat_model: str = Field(default="gpt-oss:20b")

    # Retrieval tuning
    top_k: int = Field(default=6, description="Number of chunks to retrieve")
    min_score: float = Field(default=0.25, description="Minimum similarity score")


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health")
def health():
    """
    Health check endpoint.
    
    Returns:
        Simple status indicator (doesn't test LLM or PDF processing)
    """
    return {"status": "ok", "version": "0.3.0"}


@app.get("/list-policies")
def list_policies():
    """
    List all ingested policies with their metadata.
    
    Returns:
        JSON with policies list:
        {
            "policies": [
                {
                    "policy_id": "policy-abc123",
                    "pages": 25,
                    "chunks": 85,
                    "text_chunks": 70,
                    "image_chunks": 15,
                    "embedding_model": "nomic-embed-text:latest"
                },
                ...
            ]
        }
    """
    policies = []
    
    policies_root = Path("data/policies")
    if not policies_root.exists():
        return {"policies": []}
    
    for policy_dir in policies_root.iterdir():
        if not policy_dir.is_dir():
            continue
        
        policy_id = policy_dir.name
        metadata_file = policy_dir / "metadata.json"
        
        if metadata_file.exists():
            try:
                meta = json.loads(metadata_file.read_text(encoding="utf-8"))
                
                # Check if it's a standalone image or regular policy
                policy_type = meta.get("type", "policy")
                
                policies.append({
                    "policy_id": policy_id,
                    "type": policy_type,  # NEW: "policy" or "standalone_image"
                    "pages": meta.get("pages", 1),
                    "chunks": meta.get("chunks_embedded", 0),
                    "text_chunks": meta.get("text_chunks", 0),
                    "image_chunks": meta.get("image_chunks", 0) if policy_type == "policy" else 1,
                    "embedding_model": meta.get("embedding_model", "unknown"),
                })
            except Exception:
                continue
    
    return {"policies": policies}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    pdf: UploadFile = File(...),
    policy_id: str | None = None,
    embedding_model: str = "nomic-embed-text:latest",
    vision_model: str = "llama3.2-vision:11b",
    enable_vision: bool = True,  # NEW: Toggle vision processing
):
    """
    Upload and index a policy PDF into the RAG system.
    
    NEW: Now processes both text AND images!
    
    Process:
    1. Validates file type (must be PDF)
    2. Extracts text from all pages
    3. Chunks text into overlapping segments
    4. [NEW] Extracts images and generates AI descriptions
    5. Embeds all chunks (text + image descriptions)
    6. Builds FAISS vector search index
    7. Saves everything to disk
    
    Args:
        pdf: PDF file to upload
        policy_id: Optional custom ID (auto-generated if not provided)
        embedding_model: Which model to use for embeddings
        vision_model: Which model to use for image description
        enable_vision: Whether to process images (default True)
    
    Returns:
        IngestResponse with ingestion statistics
    
    Examples:
        # With vision (default):
        curl -X POST -F "pdf=@policy.pdf" http://localhost:8000/ingest
        
        # Without vision (text only):
        curl -X POST -F "pdf=@policy.pdf" -F "enable_vision=false" http://localhost:8000/ingest
    """
    # Validate file type
    if pdf.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Upload must be a PDF")
    
    file_ext = Path(pdf.filename).suffix.lower()
    if file_ext != ".pdf":
        raise HTTPException(
            status_code=400,
            detail=f"File extension must be .pdf, got {file_ext}"
        )
    
    # Generate policy ID if not provided
    pid = policy_id or f"policy-{uuid.uuid4().hex[:10]}"
    
    # Read file content
    pdf_bytes = await pdf.read()
    
    # Save PDF to permanent storage
    pdf_path = store.write_pdf(pid, pdf_bytes)
    
    # Run the NEW ingestion pipeline (supports vision!)
    try:
        meta = ingest_policy_with_vision(
            store=store,
            ollama=ollama,
            policy_id=pid,
            pdf_path=str(pdf_path),
            embedding_model=embedding_model,
            vision_model=vision_model,
            enable_vision=enable_vision,  # NEW: Can disable vision if needed
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Return success response with detailed statistics
    return IngestResponse(
        policy_id=pid,
        pages=int(meta["pages"]),
        chunks=int(meta["chunks"]),
        text_chunks=int(meta.get("text_chunks", 0)),  # NEW
        image_chunks=int(meta.get("image_chunks", 0)),  # NEW
        embedding_model=meta["embedding_model"],
        vision_model=meta.get("vision_model"),  # NEW
    )

@app.post("/ingest-image")
async def ingest_image(
    image: UploadFile = File(...),
    image_id: str | None = None,
    vision_model: str = "llama3.2-vision:11b",
):
    """
    Upload a standalone image (JPG, PNG, etc.) for vision AI testing.
    
    This creates a special "image-only policy" that contains just this image's description.
    Great for testing what the vision model can see and describe.
    
    Args:
        image: Image file (JPG, PNG, GIF, WebP, BMP)
        image_id: Optional custom ID (auto-generated if not provided)
        vision_model: Which vision model to use
    
    Returns:
        {
            "image_id": "img-abc123",
            "description": "The AI's description of the image...",
            "vision_model": "llama3.2-vision:11b",
            "image_size_bytes": 12345
        }
    """
    # Validate file type
    allowed_types = {
        "image/jpeg", "image/jpg", "image/png", 
        "image/gif", "image/webp", "image/bmp"
    }
    
    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Must be an image file. Got: {image.content_type}"
        )
    
    # Generate image ID if not provided
    img_id = image_id or f"img-{uuid.uuid4().hex[:10]}"
    
    # Read image bytes
    image_bytes = await image.read()
    image_size = len(image_bytes)
    
    # Import the vision processor function
    from app.rag.processors.vision_processor import describe_image_with_vision
    
    # Describe the image with vision AI
    try:
        description = describe_image_with_vision(
            ollama_client=ollama,
            image_bytes=image_bytes,
            vision_model=vision_model,
        )
        
        if not description:
            raise HTTPException(
                status_code=500,
                detail="Vision model returned empty description"
            )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Vision processing failed: {str(e)}"
        )
    
    # Save the image and description as a special "image-only policy"
    # This allows it to be queried just like a regular policy
    policy_dir = store.policy_dir(f"image_{img_id}")
    
    # Save the image file
    image_path = policy_dir / "source_image.png"
    image_path.write_bytes(image_bytes)
    
    # Create a single chunk with the description
    from app.rag.types import Chunk
    chunk = Chunk(
        chunk_id=f"{img_id}_img0",
        page=1,
        text=description
    )
    
    # Embed the description
    try:
        vec = ollama.embed("nomic-embed-text:latest", description)
        
        # Build tiny FAISS index with just this one vector
        import numpy as np
        import faiss
        
        arr = np.array([vec], dtype="float32")
        faiss.normalize_L2(arr)
        dim = arr.shape[1]
        
        index = faiss.IndexFlatIP(dim)
        index.add(arr)
        
        # Save everything
        store.write_faiss_index(f"image_{img_id}", index)
        store.write_chunks(f"image_{img_id}", [chunk])
        store.write_metadata(
            f"image_{img_id}",
            {
                "type": "standalone_image",
                "image_id": img_id,
                "original_filename": image.filename,
                "image_size_bytes": image_size,
                "vision_model": vision_model,
                "description_length": len(description),
                "vector_dim": dim,
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Embedding failed: {str(e)}"
        )
    
    return {
        "image_id": img_id,
        "policy_id": f"image_{img_id}",  # Can query this like a regular policy
        "description": description,
        "vision_model": vision_model,
        "image_size_bytes": image_size,
        "original_filename": image.filename,
    }


@app.post("/ask")
def ask(req: AskRequest):
    """
    Ask a question about a specific ingested policy.
    
    Uses RAG (Retrieval Augmented Generation):
    1. Embeds the question into a vector
    2. Searches FAISS index for most similar chunks
    3. Retrieves relevant chunks (text AND image descriptions)
    4. Passes chunks to LLM as context
    5. Returns answer with page citations
    
    Returns:
        {
            "answer": "The policy states...",
            "citations": [
                {"page": 5, "chunk_id": "p5_c2", "excerpt": "..."},
                {"page": 8, "chunk_id": "p8_img0", "excerpt": "According to the diagram..."}
            ],
            "retrieved_chunk_ids": ["p5_c2", "p8_img0"]
        }
    
    Note: Citations with "img" in chunk_id are from images!
    """
    # Check if policy exists
    policy_dir = Path("data/policies") / req.policy_id
    if not policy_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown policy_id: {req.policy_id}. "
                f"Policy has not been ingested yet. Use POST /ingest first."
            )
        )
    
    # Run the query pipeline
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


# =============================================================================
# Additional Info
# =============================================================================
"""
FILE STRUCTURE CREATED BY THIS API:

data/policies/{policy_id}/
├── source.pdf           # Original uploaded PDF
├── chunks.json          # All chunks (text + image descriptions)
├── metadata.json        # Ingestion statistics and model info
└── index.faiss          # Vector search index

METADATA EXAMPLE:
{
    "pages": 25,
    "chunks_total": 85,
    "text_chunks": 70,
    "image_chunks": 15,
    "chunks_embedded": 85,
    "chunks_failed": 0,
    "embedding_model": "nomic-embed-text:latest",
    "vision_model": "llama3.2-vision:11b",
    "vector_dim": 768
}

TYPICAL WORKFLOW:
1. POST /ingest with PDF file
2. Wait for processing (may take a few minutes with vision)
3. POST /ask with questions
4. Get answers with citations to pages and chunks
"""
