"""
storage.py - Stage 1: Intake, SHA-256 digital fingerprinting, write-once vault,
working-copy isolation, and Section 63 BSA (former 65B IEA) certificate export.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config
from app.db import ForensicDB


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]+")


@dataclass(frozen=True)
class PreservedEvidence:
    evidence_id: str
    original_filename: str
    safe_filename: str
    sha256: str
    size_bytes: int
    vault_path: Path
    working_path: Path
    ingested_at: datetime


def sanitize_filename(filename: str) -> str:
    base = Path(filename or "evidence.bin").name
    cleaned = _SAFE_FILENAME_RE.sub("_", base).strip("._")
    return cleaned or "evidence.bin"


def _confine_path(base_dir: Path, target_path: Path) -> Path:
    base_resolved = base_dir.resolve()
    target_resolved = target_path.resolve()
    if target_resolved != base_resolved and not str(target_resolved).startswith(str(base_resolved) + os.sep):
        raise ValueError("Path escapes storage boundary")
    return target_resolved


def compute_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def preserve_upload(
    raw_bytes: bytes,
    filename: str,
    uploaded_by: str,
    uploader_ip: Optional[str],
    db: ForensicDB,
    case_id: Optional[str] = None,
) -> PreservedEvidence:
    """
    Stage 1:
    1. Compute SHA-256 before reading/parsing any content.
    2. Store untouched original in write-once vault (0o444).
    3. Copy to isolated workspace for downstream parsers.
    4. Record intake in append-only custody_logs.
    """
    if len(raw_bytes) == 0:
        raise ValueError("Uploaded file is empty")
    if len(raw_bytes) > config.MAX_UPLOAD_BYTES:
        raise ValueError(f"File exceeds max upload limit ({config.MAX_UPLOAD_MB} MB)")

    sha256 = compute_sha256_bytes(raw_bytes)
    now = datetime.now(timezone.utc)
    evidence_id = f"ev_{uuid.uuid4().hex[:12]}"
    safe_name = sanitize_filename(filename)

    vault_subdir = _confine_path(config.VAULT_DIR, config.VAULT_DIR / sha256)
    vault_subdir.mkdir(parents=True, exist_ok=True)
    vault_path = _confine_path(config.VAULT_DIR, vault_subdir / safe_name)

    if vault_path.exists():
        # Verify existing write-once artifact hasn't been tampered with
        existing_hash = compute_sha256_file(vault_path)
        if existing_hash != sha256:
            raise RuntimeError("Vault integrity mismatch detected for existing SHA-256")
    else:
        vault_path.write_bytes(raw_bytes)
        os.chmod(vault_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    work_subdir = _confine_path(config.WORKSPACE_DIR, config.WORKSPACE_DIR / evidence_id)
    work_subdir.mkdir(parents=True, exist_ok=True)
    working_path = _confine_path(config.WORKSPACE_DIR, work_subdir / safe_name)
    shutil.copyfile(vault_path, working_path)
    db.append_custody_log(
        log_id=f"cust_{uuid.uuid4().hex[:12]}",
        evidence_id=evidence_id,
        action="INTAKE_PRESERVED",
        actor=uploaded_by or "unknown",
        actor_ip=uploader_ip,
        sha256_at_event=sha256,
        details={
            "original_filename": filename,
            "safe_filename": safe_name,
            "size_bytes": len(raw_bytes),
            "vault_path": str(vault_path),
            "case_id": case_id,
        },
        timestamp=now,
    )

    return PreservedEvidence(
        evidence_id=evidence_id,
        original_filename=filename,
        safe_filename=safe_name,
        sha256=sha256,
        size_bytes=len(raw_bytes),
        vault_path=vault_path,
        working_path=working_path,
        ingested_at=now,
    )


def verify_vault_integrity(evidence_id: str, db: ForensicDB) -> dict:
    row = db.fetch_one("SELECT * FROM evidence_items WHERE evidence_id=?", (evidence_id,))
    if not row:
        raise FileNotFoundError(f"Evidence {evidence_id} not found")
    vault_path = Path(row["vault_path"])
    if not vault_path.exists():
        return {"evidence_id": evidence_id, "verified": False, "reason": "Vault file missing"}
    current_sha256 = compute_sha256_file(vault_path)
    verified = current_sha256 == row["sha256"]
    db.append_custody_log(
        log_id=f"cust_{uuid.uuid4().hex[:12]}",
        evidence_id=evidence_id,
        action="INTEGRITY_VERIFIED" if verified else "INTEGRITY_MISMATCH",
        actor="system",
        sha256_at_event=current_sha256,
        details={"expected_sha256": row["sha256"], "verified": verified},
    )
    return {
        "evidence_id": evidence_id,
        "expected_sha256": row["sha256"],
        "current_sha256": current_sha256,
        "verified": verified,
    }


def generate_section63_certificate(evidence_id: str, db: ForensicDB) -> dict:
    """
    Generates structured metadata supporting a Section 63 BSA / Section 65B IEA
    electronic evidence certificate (hashes, intake timestamp, custodian, audit trail).
    """
    ev = db.fetch_one("SELECT * FROM evidence_items WHERE evidence_id=?", (evidence_id,))
    if not ev:
        raise FileNotFoundError(f"Evidence {evidence_id} not found")
    integrity = verify_vault_integrity(evidence_id, db)
    custody = db.fetch_all(
        "SELECT * FROM custody_logs WHERE evidence_id=? ORDER BY timestamp ASC",
        (evidence_id,),
    )
    return {
        "certificate_standard": "Bharatiya Sakshya Adhiniyam, 2023 - Section 63 (formerly Section 65B IEA)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_id": evidence_id,
        "original_filename": ev["filename"],
        "evidence_type": ev["evidence_type"],
        "sha256_hash": ev["sha256"],
        "vault_integrity_verified": integrity["verified"],
        "ingested_at_utc": ev["ingested_at"],
        "uploaded_by": ev["uploaded_by"],
        "case_id": ev["case_id"],
        "records_extracted": ev["record_count"],
        "rejected_rows": ev["rejected_count"],
        "chain_of_custody": custody,
    }
