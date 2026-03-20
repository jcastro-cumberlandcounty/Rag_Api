"""
ordinance_rag/api/admin_router.py

Admin endpoints for managing ordinance collections.
Ingestion, re-indexing, and status checking.
These should be protected in production (role-based auth).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.rag.ollama_client import OllamaClient
from app.rag.ordinance_rag.api.models import (
    IngestRequest,
    IngestResponse,
    JurisdictionStatus,
    StatusResponse,
)
from app.rag.ordinance_rag.core.ingest import ingest_jurisdiction
from app.rag.ordinance_rag.core.store import collection_exists, get_collection_count

router = APIRouter(prefix="/ordinances/admin", tags=["Ordinance Admin"])

_ollama = OllamaClient()

JURISDICTIONS_DIR = Path(__file__).resolve().parents[2] / "jurisdictions"


def _all_jurisdiction_keys() -> list[str]:
    """Return all jurisdiction folder names that have a config.json."""
    return [
        d.name
        for d in sorted(JURISDICTIONS_DIR.iterdir())
        if d.is_dir() and (d / "config.json").exists()
    ]


def _load_config(key: str) -> dict:
    with open(JURISDICTIONS_DIR / key / "config.json", encoding="utf-8") as f:
        return json.load(f)


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest PDFs for a jurisdiction into its vector collection",
)
async def ingest(request: IngestRequest) -> IngestResponse:
    """
    Run ingestion for a jurisdiction.
    Reads all PDFs from jurisdictions/{key}/docs/, chunks, embeds, and stores.
    Set force_reindex=true to wipe and rebuild the collection.
    """
    try:
        result = ingest_jurisdiction(
            jurisdiction_key=request.jurisdiction,
            ollama_client=_ollama,
            force_reindex=request.force_reindex,
        )
        return IngestResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Check indexing status for all jurisdictions",
)
async def status() -> StatusResponse:
    """
    Returns the indexing status for every jurisdiction —
    whether it's been ingested, how many chunks are stored, and if it's ready.
    """
    statuses = []
    for key in _all_jurisdiction_keys():
        try:
            config = _load_config(key)
            collection_name = config["collection_name"]
            indexed = collection_exists(collection_name)
            count = get_collection_count(collection_name)
            statuses.append(
                JurisdictionStatus(
                    key=key,
                    display_name=config["display_name"],
                    collection_name=collection_name,
                    indexed=indexed,
                    chunk_count=count,
                    status="ready" if indexed else "not_indexed",
                )
            )
        except Exception as e:
            statuses.append(
                JurisdictionStatus(
                    key=key,
                    display_name=key,
                    collection_name="",
                    indexed=False,
                    chunk_count=0,
                    status=f"error: {str(e)}",
                )
            )
    return StatusResponse(jurisdictions=statuses)
