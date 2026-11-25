"""
routes/records.py - Query normalized canonical records (v1.1 + v1.2), provenance,
validation flags, and rejected rows.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter

from app.db import get_db

router = APIRouter(prefix="/api/v1/records", tags=["Normalized Records"])


@router.get("/transactions")
def list_transactions(
    evidence_id: Optional[str] = None,
    channel: Optional[str] = None,
    rrn: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    db = get_db()
    clauses = ["1=1"]
    params: list = []
    if evidence_id:
        clauses.append("evidence_id=?")
        params.append(evidence_id)
    if channel:
        clauses.append("channel=?")
        params.append(channel.upper())
    if rrn:
        clauses.append("rrn=?")
        params.append(rrn)
    rows = db.fetch_all(
        f"SELECT payload_json FROM transactions WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC LIMIT ? OFFSET ?",
        tuple([*params, limit, offset]),
    )
    items = [json.loads(r["payload_json"]) for r in rows]
    return {"count": len(items), "items": items}


@router.get("/calls")
def list_call_records(
    evidence_id: Optional[str] = None,
    number: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    db = get_db()
    clauses = ["1=1"]
    params: list = []
    if evidence_id:
        clauses.append("evidence_id=?")
        params.append(evidence_id)
    if number:
        clauses.append("(caller LIKE ? OR callee LIKE ? OR target_number LIKE ?)")
        like_v = f"%{number}%"
        params.extend([like_v, like_v, like_v])
    rows = db.fetch_all(
        f"SELECT payload_json FROM call_records WHERE {' AND '.join(clauses)} ORDER BY start_time ASC LIMIT ? OFFSET ?",
        tuple([*params, limit, offset]),
    )
    items = [json.loads(r["payload_json"]) for r in rows]
    return {"count": len(items), "items": items}


@router.get("/ip-sessions")
def list_ip_sessions(
    evidence_id: Optional[str] = None,
    ip: Optional[str] = None,
    msisdn: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    db = get_db()
    clauses = ["1=1"]
    params: list = []
    if evidence_id:
        clauses.append("evidence_id=?")
        params.append(evidence_id)
    if ip:
        clauses.append("(src_ip=? OR dst_ip=?)")
        params.extend([ip, ip])
    if msisdn:
        clauses.append("msisdn LIKE ?")
        params.append(f"%{msisdn}%")
    rows = db.fetch_all(
        f"SELECT payload_json FROM ip_sessions WHERE {' AND '.join(clauses)} ORDER BY start_time ASC LIMIT ? OFFSET ?",
        tuple([*params, limit, offset]),
    )
    items = [json.loads(r["payload_json"]) for r in rows]
    return {"count": len(items), "items": items}


@router.get("/device-artifacts")
def list_device_artifacts(
    evidence_id: Optional[str] = None,
    device_id: Optional[str] = None,
    artifact_type: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    db = get_db()
    clauses = ["1=1"]
    params: list = []
    if evidence_id:
        clauses.append("evidence_id=?")
        params.append(evidence_id)
    if device_id:
        clauses.append("device_id=?")
        params.append(device_id)
    if artifact_type:
        clauses.append("artifact_type=?")
        params.append(artifact_type.upper())
    rows = db.fetch_all(
        f"SELECT payload_json FROM device_artifacts WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC LIMIT ? OFFSET ?",
        tuple([*params, limit, offset]),
    )
    items = [json.loads(r["payload_json"]) for r in rows]
    return {"count": len(items), "items": items}


@router.get("/extended")
def list_extended_records(
    evidence_id: Optional[str] = None,
    record_type: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Returns v1.2 records (card_transaction, bank_kyc, cell_tower, sim_swap, dns_record, ncrp_complaint, fir_complaint, etc.)."""
    db = get_db()
    clauses = ["1=1"]
    params: list = []
    if evidence_id:
        clauses.append("evidence_id=?")
        params.append(evidence_id)
    if record_type:
        clauses.append("record_type=?")
        params.append(record_type)
    rows = db.fetch_all(
        f"SELECT record_type, payload_json FROM extended_records WHERE {' AND '.join(clauses)} ORDER BY id ASC LIMIT ? OFFSET ?",
        tuple([*params, limit, offset]),
    )
    items = [{"record_type": r["record_type"], **json.loads(r["payload_json"])} for r in rows]
    return {"count": len(items), "items": items}


@router.get("/rejected")
def list_rejected_rows(evidence_id: Optional[str] = None):
    db = get_db()
    if evidence_id:
        rows = db.fetch_all("SELECT * FROM rejected_rows WHERE evidence_id=?", (evidence_id,))
    else:
        rows = db.fetch_all("SELECT * FROM rejected_rows ORDER BY id DESC LIMIT 500")
    for r in rows:
        r["raw"] = json.loads(r.pop("raw_json")) if r.get("raw_json") else None
    return {"count": len(rows), "items": rows}


@router.get("/validation-flags")
def list_validation_flags(evidence_id: Optional[str] = None, severity: Optional[str] = None):
    db = get_db()
    clauses = ["1=1"]
    params: list = []
    if evidence_id:
        clauses.append("evidence_id=?")
        params.append(evidence_id)
    if severity:
        clauses.append("severity=?")
        params.append(severity.upper())
    rows = db.fetch_all(
        f"SELECT * FROM validation_flags WHERE {' AND '.join(clauses)} ORDER BY source_row ASC",
        tuple(params),
    )
    return {"count": len(rows), "items": rows}


@router.get("/provenance/{record_id}")
def get_record_provenance(record_id: str):
    db = get_db()
    rows = db.fetch_all("SELECT * FROM field_provenance WHERE record_id=?", (record_id,))
    return {"record_id": record_id, "fields": rows}
