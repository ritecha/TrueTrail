"""
routes/review.py - Human-in-the-loop review queue & mapping template persistence (Rung 6).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db

router = APIRouter(prefix="/api/v1", tags=["Human Review Queue"])


class ResolveReviewRequest(BaseModel):
    decision: str                   # APPROVED | REJECTED
    resolved_value: Optional[str] = None
    reviewer: str = "investigator"
    save_as_template: bool = True


@router.get("/review-queue")
def list_review_queue(status: Optional[str] = "PENDING", evidence_id: Optional[str] = None):
    db = get_db()
    clauses = ["1=1"]
    params: list = []
    if status:
        clauses.append("status=?")
        params.append(status.upper())
    if evidence_id:
        clauses.append("evidence_id=?")
        params.append(evidence_id)
    rows = db.fetch_all(
        f"SELECT * FROM review_queue WHERE {' AND '.join(clauses)} ORDER BY review_id DESC",
        tuple(params),
    )
    for r in rows:
        r["candidates"] = json.loads(r.pop("candidates_json", "[]"))
        r["sample_values"] = json.loads(r.pop("sample_values_json", "[]"))
    return {"count": len(rows), "items": rows}


@router.post("/review-queue/{review_id}/resolve")
def resolve_review_item(review_id: str, body: ResolveReviewRequest):
    db = get_db()
    item = db.fetch_one("SELECT * FROM review_queue WHERE review_id=?", (review_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")

    decision = body.decision.upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise HTTPException(status_code=400, detail="decision must be APPROVED or REJECTED")

    now_iso = datetime.now(timezone.utc).isoformat()
    resolved_val = body.resolved_value or item["recommended"]

    db.execute(
        """
        UPDATE review_queue
        SET status=?, resolved_value=?, reviewer=?, resolved_at=?
        WHERE review_id=?
        """,
        (decision, resolved_val, body.reviewer, now_iso, review_id),
    )

    # Save column mapping template so future uploads of this layout auto-map (Rung 0)
    template_saved = False
    if (
        decision == "APPROVED"
        and body.save_as_template
        and item["review_type"] == "COLUMN_MAPPING"
        and item.get("column_name")
        and resolved_val
    ):
        ev = db.fetch_one("SELECT evidence_type, sha256 FROM evidence_items WHERE evidence_id=?", (item["evidence_id"],))
        if ev:
            norm_hdr = re.sub(r"[^a-z0-9]+", "", item["column_name"].lower())
            db.execute(
                """
                INSERT OR REPLACE INTO mapping_templates
                (template_id, evidence_type, raw_header_norm, target_field, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f"tpl_{uuid.uuid4().hex[:10]}", ev["evidence_type"], norm_hdr, resolved_val, body.reviewer, now_iso),
            )
            template_saved = True
            db.append_custody_log(
                log_id=f"cust_{uuid.uuid4().hex[:12]}",
                evidence_id=item["evidence_id"],
                action="REVIEW_APPROVED_TEMPLATE_SAVED",
                actor=body.reviewer,
                sha256_at_event=ev["sha256"],
                details={"review_id": review_id, "column": item["column_name"], "mapped_to": resolved_val},
            )

    return {
        "review_id": review_id,
        "status": decision,
        "resolved_value": resolved_val,
        "template_saved": template_saved,
    }


@router.get("/mapping-templates")
def list_mapping_templates(evidence_type: Optional[str] = None):
    db = get_db()
    if evidence_type:
        rows = db.fetch_all("SELECT * FROM mapping_templates WHERE evidence_type=?", (evidence_type,))
    else:
        rows = db.fetch_all("SELECT * FROM mapping_templates ORDER BY created_at DESC")
    return {"count": len(rows), "items": rows}
