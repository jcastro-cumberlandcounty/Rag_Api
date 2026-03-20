"""
ordinance_rag/main.py

FastAPI sub-application for the ordinance RAG module.
Mounted into the main POLICY-RAG-API app via main.py at the root.

Mount example in root main.py:
    from app.rag.ordinance_rag.main import ordinance_app
    app.mount("/ordinance-rag", ordinance_app)

Or include routers directly:
    from app.rag.ordinance_rag.api.ordinance_router import router as ordinance_router
    from app.rag.ordinance_rag.api.admin_router import router as admin_router
    app.include_router(ordinance_router)
    app.include_router(admin_router)
"""

from fastapi import FastAPI
from app.rag.departments.ordinance_rag.api.ordinance_router import router as ordinance_router
from app.rag.departments.ordinance_rag.api.admin_router import router as admin_router

ordinance_app = FastAPI(
    title="Ordinance RAG",
    description="AI-powered Q&A for Cumberland County jurisdiction ordinances.",
    version="1.0.0",
)

ordinance_app.include_router(ordinance_router)
ordinance_app.include_router(admin_router)