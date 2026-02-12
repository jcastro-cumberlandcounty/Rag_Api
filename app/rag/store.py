from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List

import faiss

from app.rag.types import Chunk


class PolicyStore:
    """
    Handles all on-disk persistence for policies AND accessibility reports.

    Folder layout:
      data/policies/{policy_id}/
        source.pdf              ← Original uploaded PDF
        chunks.json             ← Text chunks for RAG
        metadata.json           ← RAG ingestion metadata
        index.faiss             ← Vector search index
      
      data/accessibility_reports/
        {report_id}.json        ← Accessibility compliance reports
    
    Why separate folders?
    - Keeps RAG learning data separate from compliance validation
    - Makes it easy to audit all accessibility checks
    - Allows checking files without ingesting them into RAG
    """

    def __init__(self, root_dir: str = "data/policies", accessibility_dir: str = "data/accessibility_reports"):
        """
        Initialize the storage system.
        
        Args:
            root_dir: Where to store policy documents and RAG data
            accessibility_dir: Where to store accessibility compliance reports
        """
        # Folder for RAG data (embeddings, chunks, etc.)
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        
        # Separate folder for accessibility reports (audit trail)
        self.accessibility_root = Path(accessibility_dir)
        self.accessibility_root.mkdir(parents=True, exist_ok=True)

    def policy_dir(self, policy_id: str) -> Path:
        """Get (or create) the directory for a specific policy."""
        d = self.root / policy_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # =========================================================================
    # PDF STORAGE (for RAG)
    # =========================================================================

    def write_pdf(self, policy_id: str, pdf_bytes: bytes) -> Path:
        """
        Save the uploaded PDF as source.pdf for provenance/audit.
        
        This is used by the RAG system to keep a copy of the original document.
        """
        d = self.policy_dir(policy_id)
        pdf_path = d / "source.pdf"
        pdf_path.write_bytes(pdf_bytes)
        return pdf_path

    # =========================================================================
    # CHUNKS STORAGE (for RAG)
    # =========================================================================

    def write_chunks(self, policy_id: str, chunks: List[Chunk]) -> Path:
        """
        Save text chunks as JSON for auditing and later retrieval.
        
        These chunks are what the RAG system searches through to answer questions.
        """
        d = self.policy_dir(policy_id)
        path = d / "chunks.json"
        data = [asdict(c) for c in chunks]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def read_chunks(self, policy_id: str) -> List[Chunk]:
        """Load previously saved chunks for a policy."""
        d = self.policy_dir(policy_id)
        path = d / "chunks.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Chunk(**item) for item in raw]

    # =========================================================================
    # METADATA STORAGE (for RAG)
    # =========================================================================

    def write_metadata(self, policy_id: str, meta: dict) -> Path:
        """
        Save metadata about the RAG ingestion process.
        
        Example metadata:
        {
            "pages": 45,
            "chunks_embedded": 120,
            "embedding_model": "nomic-embed-text:latest",
            "vector_dim": 768
        }
        """
        d = self.policy_dir(policy_id)
        path = d / "metadata.json"
        path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    def read_metadata(self, policy_id: str) -> dict:
        """Load RAG metadata for a policy."""
        d = self.policy_dir(policy_id)
        path = d / "metadata.json"
        return json.loads(path.read_text(encoding="utf-8"))

    # =========================================================================
    # FAISS INDEX STORAGE (for RAG)
    # =========================================================================

    def write_faiss_index(self, policy_id: str, index) -> Path:
        """
        Persist FAISS vector search index to disk.
        
        FAISS (Facebook AI Similarity Search) is the library that enables
        fast semantic search over document chunks.
        """
        d = self.policy_dir(policy_id)
        path = d / "index.faiss"
        faiss.write_index(index, str(path))
        return path

    def read_faiss_index(self, policy_id: str):
        """Load FAISS index from disk for searching."""
        d = self.policy_dir(policy_id)
        path = d / "index.faiss"
        if not path.exists():
            raise FileNotFoundError(f"FAISS index not found for policy_id={policy_id}")
        return faiss.read_index(str(path))

    # =========================================================================
    # ACCESSIBILITY REPORT STORAGE (NEW!)
    # =========================================================================
    # These methods handle ADA/WCAG compliance reports
    # Stored separately from RAG data for clean separation of concerns

    def write_accessibility_report(self, report_id: str, report_data: dict) -> Path:
        """
        Save an accessibility compliance report.
        
        Args:
            report_id: Unique identifier for this report (e.g., "ada_abc123")
            report_data: Dictionary containing the AccessibilityReport data
                        (usually from report.model_dump())
        
        Returns:
            Path where the report was saved
        
        Example:
            from accessibility_checker import check_file_accessibility
            
            report = check_file_accessibility("/tmp/policy.pdf")
            report_id = AccessibilityChecker.generate_report_id("policy.pdf")
            store.write_accessibility_report(report_id, report.model_dump())
        """
        # Save to data/accessibility_reports/{report_id}.json
        path = self.accessibility_root / f"{report_id}.json"
        
        # Write with pretty formatting for human readability
        path.write_text(
            json.dumps(report_data, indent=2, default=str),
            encoding="utf-8"
        )
        
        return path

    def read_accessibility_report(self, report_id: str) -> dict:
        """
        Load a previously saved accessibility report.
        
        Args:
            report_id: Unique identifier for the report
        
        Returns:
            Dictionary containing report data
        
        Raises:
            FileNotFoundError: If report doesn't exist
        """
        path = self.accessibility_root / f"{report_id}.json"
        
        if not path.exists():
            raise FileNotFoundError(
                f"Accessibility report not found: {report_id}. "
                f"Has the file been checked yet?"
            )
        
        return json.loads(path.read_text(encoding="utf-8"))

    def list_accessibility_reports(self) -> List[str]:
        """
        List all accessibility report IDs.
        
        Useful for:
        - Auditing all checked files
        - Building a compliance dashboard
        - Finding reports for cleanup
        
        Returns:
            List of report IDs (e.g., ["ada_abc123", "ada_def456"])
        """
        # Find all .json files in the accessibility reports directory
        report_files = self.accessibility_root.glob("*.json")
        
        # Extract just the report ID (filename without .json)
        report_ids = [f.stem for f in report_files]
        
        # Sort alphabetically for consistency
        return sorted(report_ids)

    def delete_accessibility_report(self, report_id: str) -> bool:
        """
        Delete an accessibility report.
        
        Args:
            report_id: Unique identifier for the report
        
        Returns:
            True if report was deleted, False if it didn't exist
        """
        path = self.accessibility_root / f"{report_id}.json"
        
        if path.exists():
            path.unlink()  # Delete the file
            return True
        
        return False

    def accessibility_report_exists(self, report_id: str) -> bool:
        """
        Check if an accessibility report exists.
        
        Args:
            report_id: Unique identifier for the report
        
        Returns:
            True if report exists, False otherwise
        """
        path = self.accessibility_root / f"{report_id}.json"
        return path.exists()
