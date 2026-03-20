"""
ordinance_rag/api/ordinance_router.py

Public-facing endpoints for asking questions about jurisdiction ordinances.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.rag.ollama_client import OllamaClient
from app.rag.ordinance_rag.api.models import QuestionRequest, QuestionResponse, Citation
from app.rag.ordinance_rag.core.query import answer_question

router = APIRouter(prefix="/ordinances", tags=["Ordinance RAG"])

_ollama = OllamaClient()


@router.post("/ask", response_model=QuestionResponse, summary="Ask a question about a jurisdiction's ordinances")
async def ask_ordinance_question(request: QuestionRequest) -> QuestionResponse:
    """
    Submit a question about a specific jurisdiction's ordinances.
    The AI will retrieve relevant sections and return a cited answer.
    Questions outside the ordinance topic will be politely refused.
    """
    try:
        result = answer_question(
            jurisdiction_key=request.jurisdiction,
            question=request.question,
            ollama_client=_ollama,
        )
        return QuestionResponse(
            answer=result["answer"],
            citations=[Citation(**c) for c in result.get("citations", [])],
            jurisdiction=result["jurisdiction"],
            display_name=result.get("display_name"),
            in_scope=result.get("in_scope", True),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
