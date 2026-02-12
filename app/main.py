from __future__ import annotations

import uuid
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

# RAG (Retrieval Augmented Generation) imports
from app.rag.ollama_client import OllamaClient
from app.rag.store import PolicyStore
from app.rag.rag_core import ingest_policy, answer_question

# NEW: Accessibility checking imports
from app.accessibility_checker import AccessibilityChecker, check_file_accessibility
from app.accessibility_models import (
    AccessibilityReport,
    AccessibilityCheckResponse,
    AccessibilityRejectionSummary,
)


# =============================================================================
# FastAPI App Setup
# =============================================================================

app = FastAPI(
    title="Policy RAG API with ADA Compliance",
    description=(
        "Closed-domain RAG service for policy documents with built-in "
        "ADA/WCAG accessibility checking. Documents must pass WCAG AA "
        "compliance before being ingested into the knowledge base."
    ),
    version="0.2.0",
)

# =============================================================================
# Initialize Storage and Clients
# =============================================================================
# These are created once when the server starts and reused across requests

# Storage for RAG data AND accessibility reports
store = PolicyStore(
    root_dir="data/policies",
    accessibility_dir="data/accessibility_reports"
)

# Ollama client for embeddings and chat
ollama = OllamaClient(base_url="http://localhost:11434")

# Accessibility checker
accessibility_checker = AccessibilityChecker()


# =============================================================================
# Response Models (Pydantic models for API responses)
# =============================================================================

class IngestResponse(BaseModel):
    """Response returned when a document is successfully ingested."""
    policy_id: str
    pages: int
    chunks: int
    embedding_model: str
    accessibility_report_id: str  # NEW: Link to the accessibility report


class AskRequest(BaseModel):
    """Request model for asking questions about a policy."""
    policy_id: str = Field(..., description="Policy identifier to query")
    question: str = Field(..., description="User question")

    # Models are configurable per request
    embedding_model: str = Field(default="nomic-embed-text:latest")
    chat_model: str = Field(default="gpt-oss:20b")

    # Retrieval tuning knobs
    top_k: int = Field(default=6)
    min_score: float = Field(default=0.25)


class CheckAccessibilityRequest(BaseModel):
    """Request model for checking a file's accessibility."""
    report_id: str = Field(
        ...,
        description="Report ID returned when file was checked or rejected"
    )


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health")
def health():
    """
    Health check endpoint.
    
    Returns basic status without checking PDFs or LLM connectivity.
    Useful for monitoring and load balancers.
    """
    return {"status": "ok"}


@app.post("/check-accessibility", response_model=AccessibilityCheckResponse)
async def check_accessibility_endpoint(
    file: UploadFile = File(...),
):
    """
    Check a file for ADA/WCAG accessibility compliance WITHOUT ingesting it.
    
    Supported file types:
    - PDF (.pdf)
    - Word documents (.docx)
    - Excel spreadsheets (.xlsx)
    
    What gets checked:
    - Tagged structure (headings, lists, tables)
    - Alt text for images
    - Text extractability (not scanned)
    - Color contrast ratios
    - Document language specified
    - Reading order/logical structure
    
    Returns:
    - Detailed accessibility report
    - Whether file meets WCAG AA standards
    - List of specific issues with remediation steps
    - Report ID for future reference
    """
    # Get file extension to determine type
    file_ext = Path(file.filename).suffix.lower()
    
    # Validate file type
    supported_types = {".pdf", ".docx", ".xlsx"}
    if file_ext not in supported_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. "
                   f"Supported types: {', '.join(supported_types)}"
        )
    
    # Save uploaded file to a temporary location for checking
    # (We use Python's tempfile module for secure temporary file handling)
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        # Read uploaded file and write to temp file
        content = await file.read()
        tmp_file.write(content)
        tmp_file_path = tmp_file.name
    
    try:
        # Run accessibility check
        report = check_file_accessibility(
            file_path=tmp_file_path,
            original_filename=file.filename
        )
        
        # Generate unique report ID for future reference
        report_id = AccessibilityChecker.generate_report_id(file.filename)
        
        # Save the report for future retrieval
        store.write_accessibility_report(report_id, report.model_dump())
        
        # Return the full detailed report
        return AccessibilityCheckResponse(report=report)
    
    finally:
        # Always clean up temporary file
        # (Even if an error occurs, we delete the temp file)
        Path(tmp_file_path).unlink(missing_ok=True)


@app.get("/check-accessibility/{report_id}", response_model=AccessibilityCheckResponse)
def get_accessibility_report(report_id: str):
    """
    Retrieve a previously generated accessibility report.
    
    Args:
        report_id: The report ID returned when file was checked
    
    Returns:
        Complete accessibility report with all details
    
    Use this endpoint to:
    - Get full details after /ingest rejection
    - Review past accessibility checks
    - Build compliance dashboards
    """
    try:
        # Load the report from storage
        report_data = store.read_accessibility_report(report_id)
        
        # Convert back to AccessibilityReport object
        report = AccessibilityReport(**report_data)
        
        return AccessibilityCheckResponse(report=report)
    
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Accessibility report not found: {report_id}"
        )


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    pdf: UploadFile = File(...),
    policy_id: str | None = None,
    embedding_model: str = "nomic-embed-text:latest",
):
    """
    Upload and index a policy document into the RAG system.
    
    IMPORTANT: Files must pass WCAG AA accessibility compliance before ingestion.
    If a file fails accessibility checks, it will be REJECTED with a summary
    of issues. Call /check-accessibility/{report_id} to get full details.
    
    Process:
    1. Check file type (must be PDF for now)
    2. Run accessibility compliance check
    3. If compliant: proceed with RAG ingestion
    4. If non-compliant: reject with summary
    
    RAG Ingestion Steps (only if accessible):
    - Saves PDF to data/policies/{policy_id}/source.pdf
    - Extracts text from pages
    - Chunks text into overlapping segments
    - Embeds chunks using Ollama
    - Builds FAISS vector search index
    """
    
    # =========================================================================
    # STEP 1: Validate file type
    # =========================================================================
    # Currently only PDFs supported for RAG ingestion
    # (Word and Excel support could be added later)
    
    if pdf.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=400,
            detail="Upload must be a PDF file"
        )
    
    # Check file extension as backup validation
    file_ext = Path(pdf.filename).suffix.lower()
    if file_ext != ".pdf":
        raise HTTPException(
            status_code=400,
            detail=f"File extension must be .pdf, got {file_ext}"
        )
    
    # =========================================================================
    # STEP 2: Generate policy ID
    # =========================================================================
    # If caller doesn't provide policy_id, generate a unique one
    
    pid = policy_id or f"policy-{uuid.uuid4().hex[:10]}"
    
    # =========================================================================
    # STEP 3: Run accessibility compliance check FIRST
    # =========================================================================
    # This is the key difference from the old version!
    # We check accessibility BEFORE ingesting into RAG
    
    # Read file content once
    pdf_bytes = await pdf.read()
    
    # Save to temporary file for accessibility checking
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(pdf_bytes)
        tmp_file_path = tmp_file.name
    
    try:
        # Check accessibility compliance
        report = check_file_accessibility(
            file_path=tmp_file_path,
            original_filename=pdf.filename
        )
        
        # Generate report ID for future reference
        report_id = AccessibilityChecker.generate_report_id(pdf.filename)
        
        # Save the accessibility report
        store.write_accessibility_report(report_id, report.model_dump())
        
        # =====================================================================
        # STEP 4: Check if file is compliant
        # =====================================================================
        # If NOT compliant: reject the ingestion and return summary
        
        if not report.is_compliant:
            # Get top 3 most critical issues for the summary
            critical_issues = [
                issue for issue in report.issues
                if issue.blocks_compliance
            ]
            top_issues = [
                issue.description
                for issue in critical_issues[:3]
            ]
            
            # Return rejection summary
            # User can call /check-accessibility/{report_id} for full details
            rejection = AccessibilityRejectionSummary(
                message=(
                    f"File '{pdf.filename}' does NOT meet WCAG AA accessibility "
                    f"standards and cannot be ingested. Found {report.total_issues} "
                    f"issue(s). Use GET /check-accessibility/{report_id} to view "
                    f"full report with remediation steps."
                ),
                is_compliant=False,
                total_issues=report.total_issues,
                critical_issues=report.critical_issues,
                report_id=report_id,
                top_issues=top_issues,
            )
            
            # Return 400 Bad Request with rejection details
            raise HTTPException(
                status_code=400,
                detail=rejection.model_dump()
            )
    
    finally:
        # Clean up temporary file
        Path(tmp_file_path).unlink(missing_ok=True)
    
    # =========================================================================
    # STEP 5: File is compliant! Proceed with RAG ingestion
    # =========================================================================
    
    # Save the PDF to permanent storage
    pdf_path = store.write_pdf(pid, pdf_bytes)
    
    # Run the RAG ingestion pipeline
    try:
        meta = ingest_policy(
            store=store,
            ollama=ollama,
            policy_id=pid,
            pdf_path=str(pdf_path),
            embedding_model=embedding_model,
        )
    except Exception as e:
        # If ingestion fails, keep the error message visible
        raise HTTPException(status_code=500, detail=str(e))
    
    # Return success response with ingestion details AND accessibility report ID
    return IngestResponse(
        policy_id=pid,
        pages=int(meta["pages"]),
        chunks=int(meta["chunks"]),
        embedding_model=meta["embedding_model"],
        accessibility_report_id=report_id,
    )


@app.post("/ask")
def ask(req: AskRequest):
    """
    Ask a question about a specific ingested policy.
    
    This endpoint uses RAG (Retrieval Augmented Generation) to:
    1. Find relevant chunks from the policy using semantic search
    2. Pass those chunks to an LLM for answer generation
    3. Return answer with citations to specific pages
    
    Returns:
    - answer (strictly grounded in the policy text)
    - citations (page numbers + text excerpts)
    - retrieved chunk IDs (for auditing)
    
    Note: Only policies that have been successfully ingested can be queried.
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
    
    # Run the RAG answer pipeline
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


@app.get("/accessibility-reports")
def list_accessibility_reports():
    """
    List all accessibility reports in the system.
    
    Useful for:
    - Building a compliance dashboard
    - Auditing all checked files
    - Finding report IDs for specific files
    
    Returns:
    - List of report IDs
    """
    report_ids = store.list_accessibility_reports()
    
    return {
        "total_reports": len(report_ids),
        "report_ids": report_ids,
    }


# =============================================================================
# Documentation Notes for API Users
# =============================================================================
"""
TYPICAL WORKFLOW:

1. Check Accessibility First (Optional but Recommended):
   POST /check-accessibility
   - Upload your file
   - Get detailed report immediately
   - Fix any issues before ingesting

2. Ingest Policy (with automatic accessibility check):
   POST /ingest
   - Upload PDF
   - System automatically checks accessibility
   - If compliant: ingests into RAG system
   - If not compliant: rejects with report ID

3. Query Policy:
   POST /ask
   - Ask questions about ingested policies
   - Get answers with citations

KEEPING RAG AND ADA SEPARATE:

Why this architecture?
- RAG learning: Focused on semantic search and question answering
- ADA checking: Focused on accessibility compliance
- Separation allows independent evolution of both systems
- Clear audit trail for compliance (in data/accessibility_reports/)
- Can check files without ingesting them (useful for testing)

File Structure:
data/
├── policies/
│   └── policy-abc123/
│       ├── source.pdf         ← Original document
│       ├── chunks.json         ← RAG text chunks
│       ├── metadata.json       ← RAG metadata
│       └── index.faiss         ← Vector search index
│
└── accessibility_reports/
    ├── ada_xyz789.json         ← Compliance report
    └── ada_def456.json         ← Another report

This keeps RAG data and compliance data in separate, clear locations.
"""
