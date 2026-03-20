"""
ordinance_rag/core/store.py

Manages ChromaDB collections for each jurisdiction.
Each jurisdiction gets its own isolated collection — no shared namespace.
"""

from __future__ import annotations

import chromadb
from chromadb.config import Settings
from pathlib import Path

# Persistent storage path for all ordinance collections
CHROMA_PATH = Path(__file__).resolve().parents[2] / "data" / "ordinance_chroma"

_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    """Return a singleton ChromaDB persistent client."""
    global _client
    if _client is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection(collection_name: str) -> chromadb.Collection:
    """
    Get or create a collection for a jurisdiction.
    Collection name comes from the jurisdiction's config.json.
    """
    client = get_client()
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def delete_collection(collection_name: str) -> bool:
    """
    Delete a jurisdiction's collection entirely.
    Used when re-indexing from scratch.
    """
    client = get_client()
    try:
        client.delete_collection(name=collection_name)
        return True
    except Exception:
        return False


def collection_exists(collection_name: str) -> bool:
    """Check whether a collection has been indexed yet."""
    client = get_client()
    try:
        col = client.get_collection(name=collection_name)
        return col.count() > 0
    except Exception:
        return False


def get_collection_count(collection_name: str) -> int:
    """Return the number of chunks stored in a collection."""
    client = get_client()
    try:
        return client.get_collection(name=collection_name).count()
    except Exception:
        return 0
