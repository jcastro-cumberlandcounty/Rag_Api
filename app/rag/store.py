from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import faiss
import numpy as np


@dataclass(frozen=True)
class StoredChunk:
    """
    A chunk that is persisted to disk (JSONL) and used for retrieval.
    """
    chunk_id: str       # stable ID (hash) for audit + traceability
    page: int           # 1-based page number (for citations)
    chunk_index: int    # order of chunk on that page
    text: str           # chunk text


class PolicyStore:
    """
    On-disk layout (auditable + deterministic):

    data/policies/{policy_id}/
      source.pdf        (optional, but recommended for provenance)
      pages.json        (page -> extracted text)
      chunks.jsonl      (one JSON object per chunk)
      index.faiss       (vector index for retrieval)
      meta.json         (settings used for ingestion: model, chunk size, etc.)
    """

    def __init__(self, root_dir: str = "data/policies"):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def policy_dir(self, policy_id: str) -> Path:
        """
        Ensure a policy directory exists and return it.
        """
        d = self.root / policy_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------- Write operations ----------

    def write_pdf(self, policy_id: str, pdf_bytes: bytes) -> Path:
        """
        Save the uploaded PDF to disk (for auditing / provenance).
        """
        d = self.policy_dir(policy_id)
        pdf_path = d / "source.pdf"
        pdf_path.write_bytes(pdf_bytes)
        return pdf_path

    def write_pages(self, policy_id: str, pages: Dict[int, str]) -> Path:
        """
        Save extracted pages as JSON:
          { "1": "...", "2": "...", ... }

        We store keys as strings for JSON compatibility.
        """
        d = self.policy_dir(policy_id)
        p = d / "pages.json"

        # Stable ordering is helpful for audits and diffs
        data = {str(k): pages[k] for k in sorted(pages.keys())}
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def write_chunks(self, policy_id: str, chunks: List[StoredChunk]) -> Path:
        """
        Save chunks in JSONL format (one chunk per line).
        JSONL is easy to stream, inspect, and diff.
        """
        d = self.policy_dir(policy_id)
        p = d / "chunks.jsonl"

        with p.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps({
                    "chunk_id": c.chunk_id,
                    "page": c.page,
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                }, ensure_ascii=False) + "\n")

        return p

    def write_meta(self, policy_id: str, meta: Dict) -> Path:
        """
        Save ingestion metadata (models used, chunk settings, counts, etc.).
        """
        d = self.policy_dir(policy_id)
        p = d / "meta.json"
        p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    # ---------- FAISS index operations ----------

    def _index_path(self, policy_id: str) -> Path:
        return self.policy_dir(policy_id) / "index.faiss"

    def write_faiss_index(self, policy_id: str, vectors: np.ndarray) -> Tuple[Path, int]:
        """
        Store a FAISS vector index for fast similarity search.

        We normalize vectors and use inner-product search, which approximates cosine similarity.
        vectors shape: [N, D] float32
        """
        assert vectors.dtype == np.float32
        n, d = vectors.shape

        # Normalize in-place to enable cosine-like similarity
        faiss.normalize_L2(vectors)

        # Simple, deterministic index: exact search (IndexFlatIP)
        index = faiss.IndexFlatIP(d)
        index.add(vectors)

        path = self._index_path(policy_id)
        faiss.write_index(index, str(path))

        return path, d

    def load_faiss_index(self, policy_id: str) -> faiss.Index:
        """
        Load the FAISS index for a policy.
        """
        path = self._index_path(policy_id)
        if not path.exists():
            raise FileNotFoundError(f"Missing index for policy_id={policy_id}")
        return faiss.read_index(str(path))

    # ---------- Read operations ----------

    def load_chunks(self, policy_id: str) -> List[StoredChunk]:
        """
        Load chunks.jsonl into memory.
        """
        p = self.policy_dir(policy_id) / "chunks.jsonl"
        if not p.exists():
            raise FileNotFoundError(f"Missing chunks for policy_id={policy_id}")

        chunks: List[StoredChunk] = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                chunks.append(StoredChunk(
                    chunk_id=obj["chunk_id"],
                    page=int(obj["page"]),
                    chunk_index=int(obj["chunk_index"]),
                    text=obj["text"],
                ))

        return chunks

    # ---------- Utilities ----------

    @staticmethod
    def stable_chunk_id(policy_id: str, page: int, chunk_index: int, text: str) -> str:
        """
        Generate a stable chunk ID (hash) so the same content always gets the same ID.
        Useful for auditing and referencing citations.
        """
        h = hashlib.sha256()
        h.update(policy_id.encode("utf-8"))
        h.update(b"|")
        h.update(str(page).encode("utf-8"))
        h.update(b"|")
        h.update(str(chunk_index).encode("utf-8"))
        h.update(b"|")
        h.update(text.encode("utf-8"))

        # Shortened hash is enough for IDs while still collision-resistant here
        return h.hexdigest()[:24]
