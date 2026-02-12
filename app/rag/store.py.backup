from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List

import faiss

from app.rag.types import Chunk


class PolicyStore:
    """
    Handles all on-disk persistence for policies.

    Folder layout:
      data/policies/{policy_id}/
        source.pdf
        chunks.json
        metadata.json
        index.faiss
    """

    def __init__(self, root_dir: str = "data/policies"):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def policy_dir(self, policy_id: str) -> Path:
        d = self.root / policy_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -------------------------
    # PDF storage
    # -------------------------

    def write_pdf(self, policy_id: str, pdf_bytes: bytes) -> Path:
        """Save the uploaded PDF as source.pdf for provenance/audit."""
        d = self.policy_dir(policy_id)
        pdf_path = d / "source.pdf"
        pdf_path.write_bytes(pdf_bytes)
        return pdf_path

    # -------------------------
    # Chunks storage
    # -------------------------

    def write_chunks(self, policy_id: str, chunks: List[Chunk]) -> Path:
        """Save chunks as JSON for auditing and later retrieval."""
        d = self.policy_dir(policy_id)
        path = d / "chunks.json"
        data = [asdict(c) for c in chunks]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def read_chunks(self, policy_id: str) -> List[Chunk]:
        d = self.policy_dir(policy_id)
        path = d / "chunks.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Chunk(**item) for item in raw]

    # -------------------------
    # Metadata storage
    # -------------------------

    def write_metadata(self, policy_id: str, meta: dict) -> Path:
        d = self.policy_dir(policy_id)
        path = d / "metadata.json"
        path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    def read_metadata(self, policy_id: str) -> dict:
        d = self.policy_dir(policy_id)
        path = d / "metadata.json"
        return json.loads(path.read_text(encoding="utf-8"))

    # -------------------------
    # FAISS index storage
    # -------------------------

    def write_faiss_index(self, policy_id: str, index) -> Path:
        """
        Persist FAISS index to disk using faiss.write_index.
        """
        d = self.policy_dir(policy_id)
        path = d / "index.faiss"
        faiss.write_index(index, str(path))
        return path

    def read_faiss_index(self, policy_id: str):
        """Load FAISS index from disk."""
        d = self.policy_dir(policy_id)
        path = d / "index.faiss"
        if not path.exists():
            raise FileNotFoundError(f"FAISS index not found for policy_id={policy_id}")
        return faiss.read_index(str(path))
