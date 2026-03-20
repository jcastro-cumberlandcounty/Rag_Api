"""
ordinance_rag/api/models.py

Pydantic schemas for all ordinance RAG API endpoints.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    jurisdiction: str = Field(
        ...,
        description="Jurisdiction key — e.g. 'county', 'wade', 'falcon'",
        examples=["county"],
    )
    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="The user's question about the ordinance",
    )


class IngestRequest(BaseModel):
    jurisdiction: str = Field(
        ...,
        description="Jurisdiction key to ingest",
    )
    force_reindex: bool = Field(
        default=False,
        description="If true, wipes existing collection and rebuilds from scratch",
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class Citation(BaseModel):
    source: str
    chunk_index: int
    relevance_score: float


class QuestionResponse(BaseModel):
    answer: str
    citations: list[Citation]
    jurisdiction: str
    display_name: Optional[str] = None
    in_scope: bool


class IngestResponse(BaseModel):
    status: str
    jurisdiction: str
    collection: Optional[str] = None
    total_chunks: Optional[int] = None
    files: Optional[list[dict]] = None
    message: Optional[str] = None


class JurisdictionStatus(BaseModel):
    key: str
    display_name: str
    collection_name: str
    indexed: bool
    chunk_count: int
    status: str         # "ready" | "not_indexed" | "error"


class StatusResponse(BaseModel):
    jurisdictions: list[JurisdictionStatus]
