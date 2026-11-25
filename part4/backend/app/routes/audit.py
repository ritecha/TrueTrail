"""
routes/audit.py - Append-only audit logs, AI interpretation logs, and investigator summary endpoint.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException

from app import ai_service
from app.db import get_db

router = APIRouter(prefix="/api/v1", tags=["Audit & AI Interpretation"])


@router.get("/audit-logs")
def list_audit_logs(evidence_id: Optional[str] = None, limit: int = 200):
    db = get_db()
    if evidence_id:
        rows = db.fetch_all(
            "SELECT * FROM custody_logs WHERE evidence_id=? ORDER BY timestamp DESC LIMIT ?",
            (evidence_id, limit),
        )
    else:
        rows = db.fetch_all("SELECT * FROM custody_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    for r in rows:
        r["details"] = json.loads(r.pop("details_json", "{}"))
    return {"count": len(rows), "items": rows}


@router.get("/ai-logs")
def list_ai_logs(evidence_id: Optional[str] = None, limit: int = 100):
    db = get_db()
    if evidence_id:
        rows = db.fetch_all(
            "SELECT * FROM ai_interpretation_logs WHERE evidence_id=? ORDER BY created_at DESC LIMIT ?",
            (evidence_id, limit),
        )
    else:
        rows = db.fetch_all("SELECT * FROM ai_interpretation_logs ORDER BY created_at DESC LIMIT ?", (limit,))
    for r in rows:
        r["output"] = json.loads(r.pop("output_json", "{}"))
    return {"count": len(rows), "items": rows}


@router.post("/evidence/{evidence_id}/summarize")
def summarize_evidence(evidence_id: str):
    """Generates a separate, logged AI-assisted (or deterministic) summary for investigator review."""
    db = get_db()
    ev = db.fetch_one("SELECT * FROM evidence_items WHERE evidence_id=?", (evidence_id,))
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence item not found")

    events = db.fetch_all(
        "SELECT event_type, timestamp, amount, status, attributes_json FROM normalized_events WHERE evidence_id=? LIMIT 30",
        (evidence_id,),
    )
    excerpt = "\n".join(
        f"{e['timestamp']} | {e['event_type']} | amt={e['amount']} | {e['status']}"
        for e in events
    )
    return ai_service.summarize_evidence_text(
        db=db,
        evidence_id=evidence_id,
        raw_text=excerpt or f"Evidence {ev['filename']} ({ev['evidence_type']})",
        evidence_type=ev["evidence_type"],
    )
