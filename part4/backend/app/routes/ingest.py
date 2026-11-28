"""
routes/ingest.py - Evidence intake, background job processing, custody & Section 63 certificate endpoints.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

from app.db import get_db
from app.pipeline import create_ingest_job, process_preserved_evidence
from app.storage import generate_section63_certificate, verify_vault_integrity

router = APIRouter(prefix="/api/v1", tags=["Intake & Custody"])


@router.post("/evidence/upload")
async def upload_evidence(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    uploaded_by: str = Form("investigator"),
    case_id: Optional[str] = Form(None),
    hint_evidence_type: Optional[str] = Form(None),
    sync: bool = Form(False),
):
    """
    Stage 1 runs immediately (SHA-256 + write-once vault + custody log).
    Stages 2-8 run in background (or synchronously if sync=true).
    """
    db = get_db()
    raw_bytes = await file.read()
    client_ip = request.client.host if request.client else None
    try:
        job_id, preserved = create_ingest_job(
            raw_bytes=raw_bytes,
            filename=file.filename or "upload.bin",
            uploaded_by=uploaded_by,
            uploader_ip=client_ip,
            db=db,
            case_id=case_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingest error: {exc}")
    if sync:
        try:
            ev = process_preserved_evidence(
                job_id=job_id,
                preserved=preserved,
                db=db,
                uploaded_by=uploaded_by,
                case_id=case_id,
                hint_evidence_type=hint_evidence_type,
            )
            return {
                "job_id": job_id,
                "evidence_id": preserved.evidence_id,
                "sha256": preserved.sha256,
                "status": "COMPLETED" if ev.evidence_type != "rejected" else "FAILED",
                "evidence": ev.model_dump(),
            }
        except Exception as exc:
            return {
                "job_id": job_id,
                "evidence_id": preserved.evidence_id,
                "filename": preserved.original_filename,
                "sha256": preserved.sha256,
                "status": "PRESERVED_PARSE_ERROR",
                "detail": str(exc),
            }

    background_tasks.add_task(
        process_preserved_evidence,
        job_id=job_id,
        preserved=preserved,
        db=db,
        uploaded_by=uploaded_by,
        case_id=case_id,
        hint_evidence_type=hint_evidence_type,
    )
    return {
        "job_id": job_id,
        "evidence_id": preserved.evidence_id,
        "filename": preserved.original_filename,
        "sha256": preserved.sha256,
        "status": "QUEUED",
        "poll_url": f"/api/v1/jobs/{job_id}",
    }


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    db = get_db()
    job = db.fetch_one("SELECT * FROM ingest_jobs WHERE job_id=?", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/evidence")
def list_evidence(case_id: Optional[str] = None, evidence_type: Optional[str] = None):
    db = get_db()
    clauses = ["1=1"]
    params: list = []
    if case_id:
        clauses.append("case_id=?")
        params.append(case_id)
    if evidence_type:
        clauses.append("evidence_type=?")
        params.append(evidence_type)
    rows = db.fetch_all(
        f"SELECT * FROM evidence_items WHERE {' AND '.join(clauses)} ORDER BY ingested_at DESC",
        tuple(params),
    )
    return {"count": len(rows), "items": rows}


@router.get("/evidence/{evidence_id}")
def get_evidence_detail(evidence_id: str):
    db = get_db()
    ev = db.fetch_one("SELECT * FROM evidence_items WHERE evidence_id=?", (evidence_id,))
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence item not found")
    return ev


@router.get("/evidence/{evidence_id}/custody")
def get_chain_of_custody(evidence_id: str):
    db = get_db()
    logs = db.fetch_all(
        "SELECT * FROM custody_logs WHERE evidence_id=? ORDER BY timestamp ASC",
        (evidence_id,),
    )
    if not logs:
        raise HTTPException(status_code=404, detail="No custody logs found for evidence_id")
    return {"evidence_id": evidence_id, "chain_of_custody": logs}


@router.get("/evidence/{evidence_id}/verify")
def verify_evidence_hash(evidence_id: str):
    db = get_db()
    try:
        return verify_vault_integrity(evidence_id, db)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Evidence item not found")


@router.get("/evidence/{evidence_id}/certificate")
def get_section63_certificate(evidence_id: str):
    db = get_db()
    try:
        cert = generate_section63_certificate(evidence_id, db)
        db.append_custody_log(
            log_id=f"cust_{uuid.uuid4().hex[:12]}",
            evidence_id=evidence_id,
            action="SECTION63_CERTIFICATE_EXPORTED",
            actor="investigator",
            sha256_at_event=cert["sha256_hash"],
            details={"verified": cert["vault_integrity_verified"]},
        )
        return cert
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Evidence item not found")
