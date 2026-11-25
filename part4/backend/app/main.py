"""
app/main.py - FastAPI entry point for the Digital Forensic Evidence Backend.
Run locally: uvicorn app.main:app --reload --port 8000
Interactive Swagger docs for frontend teammate: http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import ml_results

import config
from app.db import get_db
from app.routes import audit, correlate, ingest, records, review


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.VAULT_DIR.mkdir(parents=True, exist_ok=True)
    config.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    get_db()
    yield


app = FastAPI(
    title="Digital Forensic Evidence Normalization & Correlation API",
    version="1.2.0",
    description=(
        "Backend-only forensic intake, preservation, parsing, normalization, validation, "
        "and cross-evidence correlation engine preserving canonical v1.1 schemas."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(records.router)
app.include_router(review.router)
app.include_router(correlate.router)
app.include_router(audit.router)
app.include_router(ml_results.router)


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "schema_version": "1.1",
        "extended_schema_version": "1.2",
        "ai_provider": config.AI_PROVIDER,
    }
