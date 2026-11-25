"""
pipeline.py - Orchestrates Stages 1 through 8 of the Digital Forensic Evidence Pipeline.
Preserves v1.1 canonical entities (Transaction, CallRecord, IPSession, DeviceArtifact,
EvidenceItem, RejectedRow) and populates v1.2 extended records + canonical correlation graph.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import config
from app.classifier import classify_evidence
from app.db import ForensicDB
from app.detector import detect_file_type
from app.disambiguator import extract_entities_from_text
from app.extractors import run_extractor
from app.extractors.base import ExtractedRow, ExtractedTable, RawExtraction
from app.mapper import ColumnDecision, map_table_columns
from app.normalizer import (
    normalize_amount,
    normalize_identifier,
    normalize_ip,
    normalize_phone,
    normalize_timestamp,
)
from app.storage import PreservedEvidence, preserve_upload
from app.validator import (
    make_flag,
    validate_bank_running_balance,
    validate_date_plausibility,
    validate_ifsc,
    validate_imei,
    validate_ip,
)
from schemas import (
    BankKYCRecord,
    BankingAccessLog,
    CallRecord,
    CardTransaction,
    CellTowerRecord,
    CyberComplaintRecord,
    DeviceArtifact,
    DNSRecord,
    EvidenceItem,
    FIRRecord,
    IPAllocationLog,
    IPSession,
    ISPSubscriberRecord,
    PaymentArtifactRecord,
    RejectedRow,
    SIMChangeRecord,
    SMSRecord,
    Transaction,
    ValidationFlag,
    VPNProxyRecord,
    WalletTransaction,
)


def _update_job(
    db: ForensicDB,
    job_id: str,
    status: str,
    progress_pct: int,
    stage: str,
    error: Optional[str] = None,
) -> None:
    db.execute(
        "UPDATE ingest_jobs SET status=?, progress_pct=?, stage=?, error=?, updated_at=? WHERE job_id=?",
        (status, progress_pct, stage, error, datetime.now(timezone.utc).isoformat(), job_id),
    )


def create_ingest_job(
    raw_bytes: bytes,
    filename: str,
    uploaded_by: str,
    uploader_ip: Optional[str],
    db: ForensicDB,
    case_id: Optional[str] = None,
) -> tuple[str, PreservedEvidence]:
    """Runs Stage 1 synchronously before queuing/running Stages 2-8."""
    preserved = preserve_upload(
        raw_bytes=raw_bytes,
        filename=filename,
        uploaded_by=uploaded_by,
        uploader_ip=uploader_ip,
        db=db,
        case_id=case_id,
    )
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now_iso = preserved.ingested_at.isoformat()
    db.execute(
        """
        INSERT INTO ingest_jobs
        (job_id, evidence_id, filename, sha256, status, progress_pct, stage, error, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'QUEUED', 10, 'INTAKE_PRESERVED', NULL, ?, ?)
        """,
        (job_id, preserved.evidence_id, filename, preserved.sha256, now_iso, now_iso),
    )
    return job_id, preserved


def process_preserved_evidence(
    job_id: str,
    preserved: PreservedEvidence,
    db: ForensicDB,
    uploaded_by: str = "investigator",
    case_id: Optional[str] = None,
    hint_evidence_type: Optional[str] = None,
) -> EvidenceItem:
    ev_id = preserved.evidence_id
    fname = preserved.original_filename
    rejected_rows: list[RejectedRow] = []
    validation_flags: list[ValidationFlag] = []

    try:
        # Stage 2: Magic-byte detection
        _update_job(db, job_id, "PROCESSING", 20, "FILE_TYPE_DETECTION")
        det = detect_file_type(preserved.working_path, fname)
        if det.is_encrypted or det.is_corrupted or det.detected_format in {"unknown", "zip", "xls"}:
            reason = det.error_reason or f"Unsupported or unreadable format: {det.detected_format}"
            rej = RejectedRow(source_file=fname, source_row=0, reason=reason, raw={"detected": det.detected_format})
            _store_rejected(db, ev_id, [rej])
            ev_item = EvidenceItem(
                evidence_id=ev_id,
                filename=fname,
                sha256=preserved.sha256,
                evidence_type="rejected",
                ingested_at=preserved.ingested_at,
                record_count=0,
                rows_in=0,
                rejected_count=1,
            )
            _save_evidence_item(db, ev_item, str(preserved.vault_path), uploaded_by, case_id)
            _update_job(db, job_id, "FAILED", 100, "REJECTED_FILE", reason)
            return ev_item

        if det.extension_mismatch:
            validation_flags.append(
                make_flag(ev_id, fname, 0, "filename", "WARNING", "EXTENSION_MISMATCH",
                          f"Extension '.{det.extension}' differs from detected '{det.detected_format}'", fname)
            )

        # Stage 3: Extraction
        _update_job(db, job_id, "PROCESSING", 35, "EXTRACTION")
        extraction = run_extractor(det.detected_format, preserved.working_path)
        for warn in extraction.warnings:
            validation_flags.append(
                make_flag(ev_id, fname, 0, "file", "INFO", "EXTRACTOR_WARNING", warn)
            )

        if extraction.ocr_used and (extraction.ocr_confidence or 1.0) < config.OCR_REVIEW_THRESHOLD:
            db.execute(
                """
                INSERT INTO review_queue
                (review_id, evidence_id, source_file, column_name, source_row, review_type,
                 candidates_json, sample_values_json, recommended, confidence, status)
                VALUES (?, ?, ?, NULL, 0, 'LOW_CONFIDENCE_OCR', '[]', ?, NULL, ?, 'PENDING')
                """,
                (
                    f"rev_{uuid.uuid4().hex[:12]}",
                    ev_id,
                    fname,
                    json.dumps([b.get("text", "")[:250] for b in extraction.text_blocks[:2]]),
                    extraction.ocr_confidence or 0.0,
                ),
            )

        # Stage 4: Classification
        _update_job(db, job_id, "PROCESSING", 50, "CLASSIFICATION")
        cls_res = classify_evidence(extraction, filename=fname, hint_type=hint_evidence_type)
        ev_type = cls_res.evidence_type

        # Stage 5-8: Field Mapping, Normalization, Validation, Storage with Provenance
        _update_job(db, job_id, "PROCESSING", 70, "MAPPING_AND_NORMALIZATION")

        rows_in = 0
        record_count = 0
        duplicate_count = 0
        has_review_items = False

        if ev_type == "device" and isinstance(extraction.json_payload, dict):
            r_in, r_ok, r_rej, r_flags = _process_device_json(
                ev_id, fname, extraction.json_payload, db
            )
            rows_in += r_in
            record_count += r_ok
            rejected_rows.extend(r_rej)
            validation_flags.extend(r_flags)
        elif ev_type in {"ncrp_complaint", "fir_complaint", "txn_screenshot", "payment_receipt", "bank_kyc"} and not extraction.tables:
            r_in, r_ok, r_flags = _process_unstructured_document(
                ev_id, fname, ev_type, extraction, db
            )
            rows_in += r_in
            record_count += r_ok
            validation_flags.extend(r_flags)
        else:
            for table in extraction.tables:
                decisions, rev_items = map_table_columns(table, ev_type, ev_id, fname, db)
                if rev_items:
                    has_review_items = True
                r_in, r_ok, r_dup, r_rej, r_flags = _process_mapped_table(
                    ev_id=ev_id,
                    fname=fname,
                    ev_type=ev_type,
                    table=table,
                    decisions=decisions,
                    extraction=extraction,
                    db=db,
                )
                rows_in += r_in
                record_count += r_ok
                duplicate_count += r_dup
                rejected_rows.extend(r_rej)
                validation_flags.extend(r_flags)

            # Fallback if a structured evidence file had only text_blocks (e.g. PDF without grid borders)
            if not extraction.tables and extraction.text_blocks:
                r_in, r_ok, r_flags = _process_unstructured_document(
                    ev_id, fname, ev_type, extraction, db
                )
                rows_in += r_in
                record_count += r_ok
                validation_flags.extend(r_flags)

        # Stage 7: Persist validation flags & rejected rows
        _update_job(db, job_id, "PROCESSING", 90, "VALIDATION_AND_CORROBORATION")
        _store_rejected(db, ev_id, rejected_rows)
        _store_flags(db, validation_flags)
        _run_rrn_corroboration(db)

        ev_item = EvidenceItem(
            evidence_id=ev_id,
            filename=fname,
            sha256=preserved.sha256,
            evidence_type=ev_type,
            ingested_at=preserved.ingested_at,
            record_count=record_count,
            rows_in=rows_in,
            rejected_count=len(rejected_rows),
            duplicate_count=duplicate_count,
        )
        _save_evidence_item(db, ev_item, str(preserved.vault_path), uploaded_by, case_id)

        db.append_custody_log(
            log_id=f"cust_{uuid.uuid4().hex[:12]}",
            evidence_id=ev_id,
            action="PIPELINE_COMPLETED",
            actor="system",
            sha256_at_event=preserved.sha256,
            details={
                "evidence_type": ev_type,
                "classification_confidence": cls_res.confidence,
                "rows_in": rows_in,
                "record_count": record_count,
                "rejected_count": len(rejected_rows),
                "validation_flags": len(validation_flags),
            },
        )
        final_status = "NEEDS_REVIEW" if has_review_items else "COMPLETED"
        _update_job(db, job_id, final_status, 100, "STORED_WITH_PROVENANCE")
        return ev_item

    except Exception as exc:
        _update_job(db, job_id, "FAILED", 100, "ERROR", str(exc))
        raise


def _save_evidence_item(
    db: ForensicDB,
    ev: EvidenceItem,
    vault_path: str,
    uploaded_by: str,
    case_id: Optional[str],
) -> None:
    db.execute(
        """
        INSERT INTO evidence_items
        (evidence_id, filename, sha256, evidence_type, ingested_at, record_count,
         rows_in, rejected_count, duplicate_count, schema_version, vault_path, uploaded_by, case_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ev.evidence_id,
            ev.filename,
            ev.sha256,
            ev.evidence_type,
            ev.ingested_at.isoformat(),
            ev.record_count,
            ev.rows_in,
            ev.rejected_count,
            ev.duplicate_count,
            ev.schema_version,
            vault_path,
            uploaded_by,
            case_id,
        ),
    )


def _store_rejected(db: ForensicDB, ev_id: str, rows: list[RejectedRow]) -> None:
    if not rows:
        return
    db.executemany(
        "INSERT INTO rejected_rows (evidence_id, source_file, source_row, reason, raw_json) VALUES (?, ?, ?, ?, ?)",
        [(ev_id, r.source_file, r.source_row, r.reason, json.dumps(r.raw, default=str)) for r in rows],
    )


def _store_flags(db: ForensicDB, flags: list[ValidationFlag]) -> None:
    if not flags:
        return
    db.executemany(
        """
        INSERT INTO validation_flags
        (flag_id, evidence_id, source_file, source_row, field_name, severity, rule_name, message, raw_value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (f.flag_id, f.evidence_id, f.source_file, f.source_row, f.field_name,
             f.severity, f.rule_name, f.message, f.raw_value)
            for f in flags
        ],
    )


def _record_event_and_entities(
    db: ForensicDB,
    evidence_id: str,
    event_id: str,
    event_type: str,
    timestamp: Optional[datetime],
    amount: Optional[float],
    duration_sec: Optional[int],
    status: Optional[str],
    source_schema: str,
    source_record_id: str,
    source_file: str,
    source_row: int,
    attributes: dict[str, Any],
    entity_links: list[tuple[str, str, Optional[str], str, float]],  # (ent_type, norm_val, raw_val, role, conf)
) -> None:
    db.execute(
        """
        INSERT OR IGNORE INTO normalized_events
        (event_id, event_type, timestamp, amount, duration_sec, status,
         source_schema, source_record_id, evidence_id, source_file, source_row, attributes_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            timestamp.isoformat() if timestamp else None,
            amount,
            duration_sec,
            status,
            source_schema,
            source_record_id,
            evidence_id,
            source_file,
            source_row,
            json.dumps(attributes, default=str, ensure_ascii=False),
        ),
    )

    for ent_type, norm_val, raw_val, role, conf in entity_links:
        if not norm_val:
            continue
        is_priv, ip_ver = None, None
        if ent_type == "IP":
            norm_ip, is_priv, ip_ver = normalize_ip(norm_val)
            if not norm_ip:
                continue
            norm_val = norm_ip
        ent_id = f"ent_{uuid.uuid5(uuid.NAMESPACE_DNS, f'{ent_type}:{norm_val}').hex[:12]}"
        actual_ent_id = db.upsert_canonical_entity(
            entity_id=ent_id,
            entity_type=ent_type,
            normalized_value=norm_val,
            raw_example=raw_val or norm_val,
            is_private_ip=is_priv,
            ip_version=ip_ver,
        )
        db.execute(
            """
            INSERT INTO entity_event_links
            (link_id, entity_id, event_id, role, confidence, source_file, source_row)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"lnk_{uuid.uuid4().hex[:12]}", actual_ent_id, event_id, role, conf, source_file, source_row),
        )


def _save_provenance_batch(
    db: ForensicDB,
    evidence_id: str,
    record_id: str,
    row: ExtractedRow,
    mapped_vals: dict[str, Any],
    decisions: dict[str, ColumnDecision],
    norm_lookup: dict[str, Any],
    orig_tz: Optional[str],
    ocr_conf: Optional[float],
) -> None:
    rows_to_insert = []
    for raw_hdr, raw_val in row.values.items():
        if not raw_val:
            continue
        dec = decisions.get(raw_hdr)
        field_name = dec.target_field if (dec and dec.target_field) else f"extra.{raw_hdr}"
        conf = dec.confidence if dec else 0.5
        if ocr_conf is not None:
            conf = round(min(conf, ocr_conf), 3)
        norm_val = norm_lookup.get(field_name)
        rows_to_insert.append((
            evidence_id,
            record_id,
            field_name,
            raw_val,
            str(norm_val) if norm_val is not None else raw_val,
            conf,
            row.sheet_name or "",
            row.page,
            row.row_number,
            raw_hdr,
            orig_tz,
        ))
    if rows_to_insert:
        db.executemany(
            """
            INSERT INTO field_provenance
            (evidence_id, record_id, field_name, raw_value, normalized_value, confidence,
             source_file, source_page, source_row, source_column, original_timezone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )


def _extract_mapped_row(
    row: ExtractedRow,
    decisions: dict[str, ColumnDecision],
) -> tuple[dict[str, str], dict[str, str]]:
    mapped: dict[str, str] = {}
    extra: dict[str, str] = {}
    for raw_hdr, raw_val in row.values.items():
        dec = decisions.get(raw_hdr)
        if dec and dec.target_field:
            mapped[dec.target_field] = raw_val
        elif raw_val:
            extra[raw_hdr] = raw_val
    return mapped, extra


def _extract_bank_meta(table: ExtractedTable) -> dict[str, Optional[str]]:
    meta = {"account_no": None, "account_name": None, "ifsc": None}
    labels = config.BANK_PROFILES["default"]["meta_labels"]
    for k_raw, v_raw in table.meta_kv.items():
        kl = k_raw.lower()
        for canon, aliases in labels.items():
            if any(a.lower() in kl for a in aliases):
                meta[canon] = v_raw.strip()
    for ln in table.metadata_lines:
        for canon, aliases in labels.items():
            if meta[canon]:
                continue
            for a in aliases:
                m = re.search(rf"{re.escape(a)}\s*[:\-]\s*([^\|\n,]+)", ln, re.IGNORECASE)
                if m:
                    meta[canon] = m.group(1).strip()
    return meta


def _process_mapped_table(
    ev_id: str,
    fname: str,
    ev_type: str,
    table: ExtractedTable,
    decisions: dict[str, ColumnDecision],
    extraction: RawExtraction,
    db: ForensicDB,
) -> tuple[int, int, int, list[RejectedRow], list[ValidationFlag]]:
    rows_in = len(table.rows)
    ok_count = 0
    dup_count = 0
    rejected: list[RejectedRow] = []
    flags: list[ValidationFlag] = []
    seen_keys: set[str] = set()
    bank_txns: list[Transaction] = []
    ipdr_raw_sessions: list[IPSession] = []
    bank_meta = _extract_bank_meta(table) if ev_type == "bank_statement" else {}

    for row in table.rows:
        mapped, extra = _extract_mapped_row(row, decisions)
        try:
            if ev_type in {"upi", "bank_statement", "interbank_transfer"}:
                txn, orig_tz, row_flags = _build_transaction(
                    ev_id, fname, ev_type, row, mapped, extra, bank_meta
                )
                flags.extend(row_flags)
                dedup_k = f"{txn.txn_id}|{txn.timestamp.isoformat()}|{txn.amount}"
                if dedup_k in seen_keys:
                    dup_count += 1
                    continue
                seen_keys.add(dedup_k)

                db.execute(
                    """
                    INSERT INTO transactions
                    (evidence_id, txn_id, rrn, timestamp, channel, amount, direction,
                     sender_account, sender_vpa, receiver_account, receiver_vpa,
                     source_type, source_file, source_row, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev_id, txn.txn_id, txn.rrn, txn.timestamp.isoformat(), txn.channel,
                        txn.amount, txn.direction, txn.sender_account, txn.sender_vpa,
                        txn.receiver_account, txn.receiver_vpa, txn.source_type,
                        txn.source_file, txn.source_row, txn.model_dump_json(),
                    ),
                )
                if ev_type == "bank_statement":
                    bank_txns.append(txn)

                links = [
                    ("ACCOUNT", txn.sender_account, mapped.get("sender_account"), "remitter_account", 0.95),
                    ("ACCOUNT", txn.receiver_account, mapped.get("receiver_account"), "beneficiary_account", 0.95),
                    ("VPA", txn.sender_vpa, mapped.get("payer_vpa"), "payer_vpa", 0.95),
                    ("VPA", txn.receiver_vpa, mapped.get("payee_vpa"), "payee_vpa", 0.95),
                    ("IFSC", txn.sender_ifsc, mapped.get("sender_ifsc"), "sender_ifsc", 0.95),
                    ("IFSC", txn.receiver_ifsc, mapped.get("receiver_ifsc"), "receiver_ifsc", 0.95),
                    ("PHONE", txn.sender_mobile, mapped.get("payer_mobile"), "payer_mobile", 0.92),
                    ("UTR", txn.rrn, mapped.get("rrn"), "rrn", 0.98),
                    ("IP", txn.ip_address, mapped.get("ip"), "payer_ip", 0.92),
                    ("DEVICE_ID", txn.device_id, mapped.get("device_id"), "payer_device", 0.90),
                ]
                _record_event_and_entities(
                    db, ev_id, f"evt_{uuid.uuid4().hex[:12]}", "FINANCIAL_TRANSACTION",
                    txn.timestamp, txn.amount, None, txn.status, "Transaction",
                    txn.txn_id, fname, row.row_number,
                    {"channel": txn.channel, "direction": txn.direction, "extra": extra}, links,
                )
                _save_provenance_batch(
                    db, ev_id, txn.txn_id, row, mapped, decisions,
                    {"timestamp": txn.timestamp.isoformat(), "amount": txn.amount},
                    orig_tz, extraction.ocr_confidence,
                )
                ok_count += 1

            elif ev_type == "cdr":
                cdr, orig_tz, row_flags = _build_call_record(ev_id, fname, row, mapped)
                flags.extend(row_flags)
                db.execute(
                    """
                    INSERT INTO call_records
                    (evidence_id, record_id, start_time, caller, callee, target_number,
                     direction, call_type, imei, imsi, cell_tower_id, source_file, source_row, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev_id, cdr.record_id, cdr.start_time.isoformat(), cdr.caller, cdr.callee,
                        cdr.target_number, cdr.direction, cdr.call_type, cdr.imei, cdr.imsi,
                        cdr.cell_tower_id, cdr.source_file, cdr.source_row, cdr.model_dump_json(),
                    ),
                )
                links = [
                    ("PHONE", cdr.caller, mapped.get("calling"), "caller", 0.95),
                    ("PHONE", cdr.callee, mapped.get("called"), "callee", 0.95),
                    ("IMEI", cdr.imei, mapped.get("imei"), "handset_imei", 0.96),
                    ("IMSI", cdr.imsi, mapped.get("imsi"), "sim_imsi", 0.96),
                    ("CELL_ID", cdr.cell_tower_id, mapped.get("first_cell"), "cell_tower", 0.92),
                ]
                _record_event_and_entities(
                    db, ev_id, f"evt_{uuid.uuid4().hex[:12]}", f"CDR_{cdr.call_type}",
                    cdr.start_time, None, cdr.duration_sec, cdr.raw_type, "CallRecord",
                    cdr.record_id, fname, row.row_number, {"direction": cdr.direction, "extra": extra}, links,
                )
                ok_count += 1

            elif ev_type == "ipdr":
                sess, orig_tz, row_flags = _build_ip_session(ev_id, fname, row, mapped)
                flags.extend(row_flags)
                ipdr_raw_sessions.append(sess)

            else:
                ext_rec, ent_links, evt_type, evt_ts, evt_amt = _build_extended_record(
                    ev_id, fname, ev_type, row, mapped, extra, extraction.ocr_confidence
                )
                db.execute(
                    """
                    INSERT INTO extended_records
                    (evidence_id, record_type, record_id, timestamp, source_file, source_row, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev_id, ev_type, getattr(ext_rec, "record_id", getattr(ext_rec, "log_id", f"rec_{row.row_number}")),
                        evt_ts.isoformat() if evt_ts else None, fname, row.row_number, ext_rec.model_dump_json(),
                    ),
                )
                _record_event_and_entities(
                    db, ev_id, f"evt_{uuid.uuid4().hex[:12]}", evt_type,
                    evt_ts, evt_amt, None, getattr(ext_rec, "status", None),
                    type(ext_rec).__name__,
                    getattr(ext_rec, "record_id", getattr(ext_rec, "log_id", str(row.row_number))),
                    fname, row.row_number, {"extra": extra}, ent_links,
                )
                ok_count += 1

        except Exception as exc:
            rejected.append(RejectedRow(source_file=fname, source_row=row.row_number, reason=str(exc), raw=row.values))

    if ev_type == "bank_statement" and bank_txns:
        flags.extend(validate_bank_running_balance(bank_txns, ev_id))

    if ev_type == "ipdr" and ipdr_raw_sessions:
        merged_sessions = _merge_ipdr_sessions(ipdr_raw_sessions)
        for sess in merged_sessions:
            db.execute(
                """
                INSERT INTO ip_sessions
                (evidence_id, record_id, start_time, msisdn, imei, imsi, src_ip, dst_ip,
                 source_file, source_row, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev_id, sess.record_id, sess.start_time.isoformat(), sess.msisdn,
                    sess.imei, sess.imsi, sess.src_ip, sess.dst_ip,
                    sess.source_file, sess.source_row, sess.model_dump_json(),
                ),
            )
            links = [
                ("PHONE", sess.msisdn, sess.msisdn, "subscriber", 0.95),
                ("IP", sess.src_ip, sess.src_ip, "public_ip", 0.98),
                ("IP", sess.dst_ip, sess.dst_ip, "destination_ip", 0.90),
                ("IMEI", sess.imei, sess.imei, "handset_imei", 0.95),
                ("IMSI", sess.imsi, sess.imsi, "sim_imsi", 0.95),
                ("CELL_ID", sess.cell_id, sess.cell_id, "cell_tower", 0.90),
            ]
            _record_event_and_entities(
                db, ev_id, f"evt_{uuid.uuid4().hex[:12]}", "IP_SESSION",
                sess.start_time, None, None, sess.app_hint, "IPSession",
                sess.record_id, fname, sess.source_row, {"chunks": sess.chunks}, links,
            )
            ok_count += 1

    return rows_in, ok_count, dup_count, rejected, flags


def _build_transaction(
    ev_id: str,
    fname: str,
    ev_type: str,
    row: ExtractedRow,
    mapped: dict[str, str],
    extra: dict[str, str],
    bank_meta: dict[str, Optional[str]],
) -> tuple[Transaction, Optional[str], list[ValidationFlag]]:
    flags: list[ValidationFlag] = []
    if ev_type == "upi":
        ts, orig_tz = normalize_timestamp(mapped.get("timestamp"), config.UPI["assume_tz"])
        if not ts:
            raise ValueError("Missing or unparseable timestamp")
        amt, _ = normalize_amount(mapped.get("amount"))
        if not amt or amt <= 0:
            raise ValueError("Invalid or non-positive amount")
        txn_id = normalize_identifier(mapped.get("txn_id")) or f"upi_{ev_id}_{row.row_number}"
        rrn = normalize_identifier(mapped.get("rrn"))
        sender_ifsc = normalize_identifier(mapped.get("payer_ifsc"))
        receiver_ifsc = normalize_identifier(mapped.get("payee_ifsc"))
        ip_str, _, _ = normalize_ip(mapped.get("ip"))

        flags.extend(validate_date_plausibility(ts, ev_id, fname, row.row_number, "timestamp"))
        flags.extend(validate_ifsc(sender_ifsc, ev_id, fname, row.row_number, "sender_ifsc"))
        flags.extend(validate_ifsc(receiver_ifsc, ev_id, fname, row.row_number, "receiver_ifsc"))
        if mapped.get("ip") and not ip_str:
            flags.extend(validate_ip(mapped.get("ip"), ev_id, fname, row.row_number, "ip_address"))

        txn = Transaction(
            txn_id=txn_id,
            rrn=rrn,
            timestamp=ts,
            channel="UPI",
            amount=float(amt),
            currency=normalize_identifier(mapped.get("currency")) or "INR",
            sender_account=normalize_identifier(mapped.get("payer_account")),
            sender_vpa=normalize_identifier(mapped.get("payer_vpa")),
            sender_ifsc=sender_ifsc,
            sender_name=normalize_identifier(mapped.get("payer_name")),
            sender_mobile=normalize_phone(mapped.get("payer_mobile")),
            receiver_account=normalize_identifier(mapped.get("payee_account")),
            receiver_vpa=normalize_identifier(mapped.get("payee_vpa")),
            receiver_ifsc=receiver_ifsc,
            receiver_name=normalize_identifier(mapped.get("payee_name")),
            device_id=normalize_identifier(mapped.get("device_id")),
            ip_address=ip_str,
            app_name=normalize_identifier(mapped.get("app_name")),
            status=(normalize_identifier(mapped.get("status")) or "SUCCESS").upper(),
            response_code=normalize_identifier(mapped.get("response_code")),
            remarks=normalize_identifier(mapped.get("remarks")),
            source_type="UPI_LOG",
            source_file=fname,
            source_row=row.row_number,
        )
        return txn, orig_tz, flags

    # bank_statement or interbank_transfer
    prof = config.BANK_PROFILES["default"]
    ts_raw = mapped.get("txn_date") or mapped.get("timestamp")
    ts, orig_tz = normalize_timestamp(ts_raw, prof["assume_tz"], prof["date_formats"])
    if not ts:
        raise ValueError("Missing or unparseable bank transaction timestamp")

    debit_amt, _ = normalize_amount(mapped.get("debit"))
    credit_amt, _ = normalize_amount(mapped.get("credit"))
    single_amt, inferred_dir = normalize_amount(mapped.get("amount"))

    direction: Optional[str] = None
    if debit_amt and debit_amt > 0:
        amount = float(debit_amt)
        direction = "DEBIT"
    elif credit_amt and credit_amt > 0:
        amount = float(credit_amt)
        direction = "CREDIT"
    elif single_amt and single_amt > 0:
        amount = float(single_amt)
        direction = inferred_dir
    else:
        raise ValueError("Missing valid debit/credit/amount")

    narration = normalize_identifier(mapped.get("narration") or mapped.get("remarks"))
    bal_dec, _ = normalize_amount(mapped.get("balance"))
    channel = "OTHER"
    chan_raw = (mapped.get("channel") or "").upper().strip()
    if chan_raw in {"UPI", "IMPS", "NEFT", "RTGS", "ATM"}:
        channel = chan_raw
    elif narration:
        for pat, ch in prof["channel_rules"]:
            if re.search(pat, narration, re.IGNORECASE):
                channel = ch
                break

    rrn = normalize_identifier(mapped.get("rrn") or mapped.get("ref_no"))
    sender_acc = normalize_identifier(mapped.get("sender_account"))
    receiver_acc = normalize_identifier(mapped.get("receiver_account"))
    sender_ifsc = normalize_identifier(mapped.get("sender_ifsc"))
    receiver_ifsc = normalize_identifier(mapped.get("receiver_ifsc"))
    sender_name = normalize_identifier(mapped.get("sender_name"))
    receiver_name = normalize_identifier(mapped.get("receiver_name"))
    receiver_vpa = None
    sender_vpa = None
    remarks = normalize_identifier(mapped.get("remarks"))

    if ev_type == "bank_statement":
        stmt_acc = bank_meta.get("account_no")
        stmt_name = bank_meta.get("account_name")
        stmt_ifsc = bank_meta.get("ifsc")
        if direction == "DEBIT":
            sender_acc = sender_acc or stmt_acc
            sender_name = sender_name or stmt_name
            sender_ifsc = sender_ifsc or stmt_ifsc
        elif direction == "CREDIT":
            receiver_acc = receiver_acc or stmt_acc
            receiver_name = receiver_name or stmt_name
            receiver_ifsc = receiver_ifsc or stmt_ifsc

    # Parse UPI narration & free text entities
    if narration:
        m_upi = re.match(prof["upi_narration"], narration)
        if m_upi:
            rrn = rrn or m_upi.group("rrn")
            remarks = remarks or m_upi.group("remark") or None
            if direction == "DEBIT":
                receiver_name = receiver_name or m_upi.group("name").strip()
                receiver_vpa = m_upi.group("vpa")
                receiver_ifsc = receiver_ifsc or m_upi.group("ifsc")
            else:
                sender_name = sender_name or m_upi.group("name").strip()
                sender_vpa = m_upi.group("vpa")
                sender_ifsc = sender_ifsc or m_upi.group("ifsc")
        else:
            for ent in extract_entities_from_text(narration, fname, row.row_number):
                if ent["entity_type"] == "UTR" and not rrn:
                    rrn = ent["extracted_value"]
                elif ent["entity_type"] == "VPA":
                    if direction == "DEBIT" and not receiver_vpa:
                        receiver_vpa = ent["extracted_value"]
                    elif direction == "CREDIT" and not sender_vpa:
                        sender_vpa = ent["extracted_value"]

    txn_id = normalize_identifier(mapped.get("txn_id")) or rrn or f"bk_{ev_id}_{row.row_number}"
    flags.extend(validate_date_plausibility(ts, ev_id, fname, row.row_number, "timestamp"))
    flags.extend(validate_ifsc(sender_ifsc, ev_id, fname, row.row_number, "sender_ifsc"))
    flags.extend(validate_ifsc(receiver_ifsc, ev_id, fname, row.row_number, "receiver_ifsc"))

    txn = Transaction(
        txn_id=txn_id,
        rrn=rrn,
        timestamp=ts,
        channel=channel,  # type: ignore[arg-type]
        amount=amount,
        currency="INR",
        direction=direction,  # type: ignore[arg-type]
        sender_account=sender_acc,
        sender_vpa=sender_vpa,
        sender_ifsc=sender_ifsc,
        sender_name=sender_name,
        receiver_account=receiver_acc,
        receiver_vpa=receiver_vpa,
        receiver_ifsc=receiver_ifsc,
        receiver_name=receiver_name,
        status=(normalize_identifier(mapped.get("status")) or "SUCCESS").upper(),
        remarks=remarks,
        narration=narration,
        balance_after=float(bal_dec) if bal_dec is not None else None,
        source_type="BANK_STATEMENT",
        source_file=fname,
        source_row=row.row_number,
    )
    return txn, orig_tz, flags


def _build_call_record(
    ev_id: str,
    fname: str,
    row: ExtractedRow,
    mapped: dict[str, str],
) -> tuple[CallRecord, Optional[str], list[ValidationFlag]]:
    flags: list[ValidationFlag] = []
    ts, orig_tz = normalize_timestamp(mapped.get("start"), config.CDR["assume_tz"])
    if not ts:
        raise ValueError("Missing or invalid CDR start timestamp")
    callee = normalize_phone(mapped.get("called"))
    if not callee:
        raise ValueError("Missing called number")
    caller = normalize_phone(mapped.get("calling"))

    raw_type = (normalize_identifier(mapped.get("call_type")) or "MOC").upper()
    direction = config.CDR_DIRECTION.get(raw_type, "OUT")
    svc_raw = (normalize_identifier(mapped.get("service")) or ("SMS" if "SMS" in raw_type else "VOICE")).upper()
    call_type = config.CDR_SERVICE.get(svc_raw, "VOICE")
    dur = int(float(mapped.get("duration") or 0))
    target_num = caller if config.CDR_TARGET_IS_CALLER.get(direction, True) else callee
    imei = normalize_identifier(mapped.get("imei"))

    flags.extend(validate_date_plausibility(ts, ev_id, fname, row.row_number, "start_time"))
    flags.extend(validate_imei(imei, ev_id, fname, row.row_number))

    cdr = CallRecord(
        record_id=f"cdr_{ev_id}_{row.row_number}",
        start_time=ts,
        duration_sec=max(0, dur),
        caller=caller,
        callee=callee,
        target_number=target_num,
        direction=direction,  # type: ignore[arg-type]
        call_type=call_type,  # type: ignore[arg-type]
        raw_type=raw_type,
        imei=imei,
        imsi=normalize_identifier(mapped.get("imsi")),
        cell_tower_id=normalize_identifier(mapped.get("first_cell")),
        last_cell_id=normalize_identifier(mapped.get("last_cell")),
        lac=normalize_identifier(mapped.get("lac")),
        latitude=float(mapped["lat"]) if mapped.get("lat") else None,
        longitude=float(mapped["lon"]) if mapped.get("lon") else None,
        tower_address=normalize_identifier(mapped.get("address")),
        source_file=fname,
        source_row=row.row_number,
    )
    return cdr, orig_tz, flags


def _build_ip_session(
    ev_id: str,
    fname: str,
    row: ExtractedRow,
    mapped: dict[str, str],
) -> tuple[IPSession, Optional[str], list[ValidationFlag]]:
    flags: list[ValidationFlag] = []
    start_ts, orig_tz = normalize_timestamp(mapped.get("start"), config.IPDR["assume_tz"], config.IPDR["date_formats"])
    if not start_ts:
        raise ValueError("Missing or invalid IPDR start timestamp")
    end_ts, _ = normalize_timestamp(mapped.get("end"), config.IPDR["assume_tz"], config.IPDR["date_formats"])
    src_ip, _, _ = normalize_ip(mapped.get("public_ip"))
    if not src_ip:
        raise ValueError("Missing or invalid public IP")

    dst_ip, _, _ = normalize_ip(mapped.get("dst_ip"))
    dst_port = int(mapped["dst_port"]) if mapped.get("dst_port") and mapped["dst_port"].isdigit() else None
    app_hint = config.APP_SIGNATURES.get((dst_ip, dst_port)) if (dst_ip and dst_port) else None

    imei = normalize_identifier(mapped.get("imei"))
    flags.extend(validate_imei(imei, ev_id, fname, row.row_number))
    flags.extend(validate_date_plausibility(start_ts, ev_id, fname, row.row_number, "start_time"))

    sess = IPSession(
        record_id=f"ipdr_{ev_id}_{row.row_number}",
        start_time=start_ts,
        end_time=end_ts,
        msisdn=normalize_phone(mapped.get("msisdn")),
        imei=imei,
        imsi=normalize_identifier(mapped.get("imsi")),
        private_ip=normalize_ip(mapped.get("private_ip"))[0],
        src_ip=src_ip,
        src_port=int(mapped["src_port"]) if mapped.get("src_port") and mapped["src_port"].isdigit() else None,
        dst_ip=dst_ip,
        dst_port=dst_port,
        protocol=normalize_identifier(mapped.get("protocol")),
        bytes_up=int(mapped["up"]) if mapped.get("up") and mapped["up"].isdigit() else None,
        bytes_down=int(mapped["down"]) if mapped.get("down") and mapped["down"].isdigit() else None,
        apn=normalize_identifier(mapped.get("apn")),
        cell_id=normalize_identifier(mapped.get("cell_id")),
        app_hint=app_hint,
        source_file=fname,
        source_row=row.row_number,
    )
    return sess, orig_tz, flags


def _merge_ipdr_sessions(sessions: list[IPSession]) -> list[IPSession]:
    ordered = sorted(sessions, key=lambda s: (s.msisdn or "", s.src_ip, s.dst_ip or "", s.dst_port or 0, s.start_time))
    merged: list[IPSession] = []
    for cur in ordered:
        if not merged:
            merged.append(cur)
            continue
        prev = merged[-1]
        same_flow = (
            prev.msisdn == cur.msisdn
            and prev.src_ip == cur.src_ip
            and prev.dst_ip == cur.dst_ip
            and prev.dst_port == cur.dst_port
        )
        prev_end = prev.end_time or prev.start_time
        gap = (cur.start_time - prev_end).total_seconds()
        if same_flow and 0 <= gap <= config.IPDR_MERGE_GAP_SEC:
            prev.end_time = max(prev_end, cur.end_time or cur.start_time)
            prev.bytes_up = (prev.bytes_up or 0) + (cur.bytes_up or 0)
            prev.bytes_down = (prev.bytes_down or 0) + (cur.bytes_down or 0)
            prev.chunks += 1
        else:
            merged.append(cur)
    return merged


def _build_extended_record(
    ev_id: str,
    fname: str,
    ev_type: str,
    row: ExtractedRow,
    mapped: dict[str, str],
    extra: dict[str, str],
    ocr_conf: Optional[float],
):
    rec_id = f"{ev_type[:4]}_{ev_id}_{row.row_number}"
    links: list[tuple[str, str, Optional[str], str, float]] = []

    if ev_type == "card_transaction":
        ts, _ = normalize_timestamp(mapped.get("timestamp"), config.IST)
        if not ts:
            raise ValueError("Missing card transaction timestamp")
        amt, _ = normalize_amount(mapped.get("amount"))
        if not amt:
            raise ValueError("Missing card transaction amount")
        card = normalize_identifier(mapped.get("masked_card_number")) or "UNKNOWN"
        rec = CardTransaction(
            record_id=rec_id, masked_card_number=card, txn_id=normalize_identifier(mapped.get("txn_id")),
            merchant_id=normalize_identifier(mapped.get("merchant_id")),
            terminal_id=normalize_identifier(mapped.get("terminal_id")),
            acquiring_bank=normalize_identifier(mapped.get("acquiring_bank")),
            amount=float(amt), currency=normalize_identifier(mapped.get("currency")) or "INR",
            timestamp=ts, auth_code=normalize_identifier(mapped.get("auth_code")),
            status=(normalize_identifier(mapped.get("status")) or "SUCCESS").upper(),
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.append(("CARD", card, mapped.get("masked_card_number"), "card_used", 0.95))
        return rec, links, "CARD_TRANSACTION", ts, float(amt)

    if ev_type in {"internet_banking_log", "mobile_banking_log"}:
        ts, _ = normalize_timestamp(mapped.get("login_timestamp"), config.IST)
        if not ts:
            raise ValueError("Missing banking login timestamp")
        ip_str, _, _ = normalize_ip(mapped.get("source_ip"))
        mob = normalize_phone(mapped.get("registered_mobile"))
        dev = normalize_identifier(mapped.get("device_id"))
        acc = normalize_identifier(mapped.get("account_id"))
        rec = BankingAccessLog(
            log_id=rec_id,
            channel="MOBILE_BANKING" if ev_type == "mobile_banking_log" else "INTERNET_BANKING",
            customer_id=normalize_identifier(mapped.get("customer_id")),
            account_id=acc, registered_mobile=mob, login_timestamp=ts, source_ip=ip_str,
            session_id=normalize_identifier(mapped.get("session_id")),
            device_id=dev,
            device_browser_info=normalize_identifier(mapped.get("device_browser_info")),
            app_version=normalize_identifier(mapped.get("app_version")),
            auth_event=normalize_identifier(mapped.get("auth_event")),
            txn_id=normalize_identifier(mapped.get("txn_id")),
            txn_details=normalize_identifier(mapped.get("txn_details")),
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("IP", ip_str or "", mapped.get("source_ip"), "login_ip", 0.95),
            ("PHONE", mob or "", mapped.get("registered_mobile"), "registered_mobile", 0.95),
            ("DEVICE_ID", dev or "", mapped.get("device_id"), "device_fingerprint", 0.92),
            ("ACCOUNT", acc or "", mapped.get("account_id"), "account_id", 0.92),
        ])
        return rec, links, "BANKING_ACCESS", ts, None

    if ev_type == "wallet_record":
        ts, _ = normalize_timestamp(mapped.get("timestamp"), config.IST)
        if not ts:
            raise ValueError("Missing wallet timestamp")
        amt, _ = normalize_amount(mapped.get("amount"))
        if not amt:
            raise ValueError("Missing wallet amount")
        mob = normalize_phone(mapped.get("mobile_number"))
        linked_acc = normalize_identifier(mapped.get("linked_bank_account"))
        ref = normalize_identifier(mapped.get("txn_ref"))
        rec = WalletTransaction(
            record_id=rec_id, wallet_id=normalize_identifier(mapped.get("wallet_id")),
            kyc_details=normalize_identifier(mapped.get("kyc_details")),
            mobile_number=mob, txn_ref=ref,
            sender=normalize_identifier(mapped.get("sender")),
            receiver=normalize_identifier(mapped.get("receiver")),
            amount=float(amt), timestamp=ts, linked_bank_account=linked_acc,
            status=(normalize_identifier(mapped.get("status")) or "SUCCESS").upper(),
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("PHONE", mob or "", mapped.get("mobile_number"), "wallet_mobile", 0.94),
            ("ACCOUNT", linked_acc or "", mapped.get("linked_bank_account"), "linked_bank_account", 0.92),
            ("UTR", ref or "", mapped.get("txn_ref"), "wallet_ref", 0.90),
        ])
        return rec, links, "WALLET_TRANSACTION", ts, float(amt)

    if ev_type == "bank_kyc":
        open_dt, _ = normalize_timestamp(mapped.get("account_opening_date"), config.IST)
        acc = normalize_identifier(mapped.get("account_number"))
        pan = normalize_identifier(mapped.get("pan"))
        mob = normalize_phone(mapped.get("registered_mobile"))
        ifsc = normalize_identifier(mapped.get("ifsc"))
        email = normalize_identifier(mapped.get("email"))
        name = normalize_identifier(mapped.get("account_holder_name"))
        rec = BankKYCRecord(
            record_id=rec_id, account_number=acc, ifsc=ifsc, account_holder_name=name,
            address=normalize_identifier(mapped.get("address")),
            dob=normalize_identifier(mapped.get("dob")), pan=pan,
            masked_aadhaar=normalize_identifier(mapped.get("masked_aadhaar")),
            registered_mobile=mob, email=email, account_opening_date=open_dt,
            kyc_verification_details=normalize_identifier(mapped.get("kyc_verification_details")),
            ocr_confidence=ocr_conf, extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("ACCOUNT", acc or "", mapped.get("account_number"), "kyc_account", 0.98),
            ("PAN", pan or "", mapped.get("pan"), "kyc_pan", 0.98),
            ("PHONE", mob or "", mapped.get("registered_mobile"), "kyc_mobile", 0.96),
            ("IFSC", ifsc or "", mapped.get("ifsc"), "branch_ifsc", 0.95),
            ("EMAIL", email or "", mapped.get("email"), "kyc_email", 0.94),
            ("PERSON", name or "", mapped.get("account_holder_name"), "account_holder", 0.85),
        ])
        return rec, links, "BANK_KYC", open_dt, None

    if ev_type == "cell_tower":
        ts, _ = normalize_timestamp(mapped.get("timestamp"), config.IST)
        if not ts:
            raise ValueError("Missing cell tower timestamp")
        cell = normalize_identifier(mapped.get("cell_id")) or "UNKNOWN"
        mob = normalize_phone(mapped.get("msisdn"))
        imei = normalize_identifier(mapped.get("imei"))
        imsi = normalize_identifier(mapped.get("imsi"))
        rec = CellTowerRecord(
            record_id=rec_id, cell_id=cell, lac=normalize_identifier(mapped.get("lac")),
            sector_id=normalize_identifier(mapped.get("sector_id")),
            latitude=float(mapped["latitude"]) if mapped.get("latitude") else None,
            longitude=float(mapped["longitude"]) if mapped.get("longitude") else None,
            tower_address=normalize_identifier(mapped.get("tower_address")),
            timestamp=ts, msisdn=mob, imei=imei, imsi=imsi,
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("CELL_ID", cell, mapped.get("cell_id"), "tower_ping", 0.96),
            ("PHONE", mob or "", mapped.get("msisdn"), "subscriber", 0.94),
            ("IMEI", imei or "", mapped.get("imei"), "handset_imei", 0.95),
            ("IMSI", imsi or "", mapped.get("imsi"), "sim_imsi", 0.95),
        ])
        return rec, links, "CELL_LOCATION_PING", ts, None

    if ev_type == "sim_swap":
        act_ts, _ = normalize_timestamp(mapped.get("activation_time"), config.IST)
        req_ts, _ = normalize_timestamp(mapped.get("replacement_request_time"), config.IST)
        mob = normalize_phone(mapped.get("msisdn")) or "UNKNOWN"
        old_i = normalize_identifier(mapped.get("old_imsi"))
        new_i = normalize_identifier(mapped.get("new_imsi"))
        rec = SIMChangeRecord(
            record_id=rec_id, msisdn=mob, old_imsi=old_i, new_imsi=new_i,
            activation_time=act_ts, replacement_request_time=req_ts,
            subscriber_details=normalize_identifier(mapped.get("subscriber_details")),
            request_channel=normalize_identifier(mapped.get("request_channel")),
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("PHONE", mob, mapped.get("msisdn"), "sim_swap_target", 0.97),
            ("IMSI", old_i or "", mapped.get("old_imsi"), "old_imsi", 0.96),
            ("IMSI", new_i or "", mapped.get("new_imsi"), "new_imsi", 0.96),
        ])
        return rec, links, "SIM_SWAP", act_ts or req_ts, None

    if ev_type == "sms_record":
        ts, _ = normalize_timestamp(mapped.get("timestamp"), config.IST)
        if not ts:
            raise ValueError("Missing SMS timestamp")
        snd = normalize_phone(mapped.get("sender_number"))
        rcv = normalize_phone(mapped.get("receiver_number"))
        rec = SMSRecord(
            record_id=rec_id, message_id=normalize_identifier(mapped.get("message_id")),
            sender_number=snd, receiver_number=rcv, timestamp=ts,
            delivery_status=normalize_identifier(mapped.get("delivery_status")),
            sms_category=normalize_identifier(mapped.get("sms_category")),
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("PHONE", snd or "", mapped.get("sender_number"), "sms_sender", 0.95),
            ("PHONE", rcv or "", mapped.get("receiver_number"), "sms_receiver", 0.95),
        ])
        return rec, links, "SMS_RECORD", ts, None

    if ev_type == "isp_subscriber":
        c_start, _ = normalize_timestamp(mapped.get("connection_start"), config.IST)
        c_end, _ = normalize_timestamp(mapped.get("connection_end"), config.IST)
        ip_str, _, _ = normalize_ip(mapped.get("assigned_ip"))
        name = normalize_identifier(mapped.get("subscriber_name"))
        rec = ISPSubscriberRecord(
            record_id=rec_id, customer_id=normalize_identifier(mapped.get("customer_id")),
            subscriber_name=name,
            registered_address=normalize_identifier(mapped.get("registered_address")),
            ip_allocation_details=normalize_identifier(mapped.get("ip_allocation_details")),
            assigned_ip=ip_str, connection_start=c_start, connection_end=c_end,
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("IP", ip_str or "", mapped.get("assigned_ip"), "isp_assigned_ip", 0.96),
            ("PERSON", name or "", mapped.get("subscriber_name"), "isp_subscriber", 0.85),
        ])
        return rec, links, "ISP_SUBSCRIBER", c_start, None

    if ev_type == "ip_allocation":
        s_start, orig_tz = normalize_timestamp(mapped.get("session_start"), config.UTC)
        if not s_start:
            raise ValueError("Missing IP allocation session_start")
        s_end, _ = normalize_timestamp(mapped.get("session_end"), config.UTC)
        pub_ip, _, _ = normalize_ip(mapped.get("public_ip"))
        priv_ip, _, _ = normalize_ip(mapped.get("private_ip"))
        sub_id = normalize_identifier(mapped.get("subscriber_id"))
        rec = IPAllocationLog(
            record_id=rec_id, subscriber_id=sub_id, public_ip=pub_ip, private_ip=priv_ip,
            port_number=int(mapped["port_number"]) if mapped.get("port_number") and mapped["port_number"].isdigit() else None,
            session_start=s_start, session_end=s_end,
            original_timestamp=mapped.get("session_start"),
            original_timezone=mapped.get("original_timezone") or orig_tz,
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("IP", pub_ip or "", mapped.get("public_ip"), "public_ip", 0.97),
            ("OTHER", sub_id or "", mapped.get("subscriber_id"), "subscriber_id", 0.90),
        ])
        return rec, links, "IP_ALLOCATION", s_start, None

    if ev_type == "dns_record":
        q_ts, _ = normalize_timestamp(mapped.get("query_timestamp"), config.UTC)
        if not q_ts:
            raise ValueError("Missing DNS query timestamp")
        dom = normalize_identifier(mapped.get("domain") or mapped.get("queried_hostname")) or "unknown"
        res_ip, _, _ = normalize_ip(mapped.get("resolved_ip"))
        rec = DNSRecord(
            record_id=rec_id, domain=dom,
            queried_hostname=normalize_identifier(mapped.get("queried_hostname")),
            resolved_ip=res_ip, query_timestamp=q_ts,
            record_type=normalize_identifier(mapped.get("record_type")),
            extra=extra, source_file=fname, source_row=row.row_number,
        )
        links.extend([
            ("DOMAIN", dom.lower(), mapped.get("domain"), "queried_domain", 0.95),
            ("IP", res_ip or "", mapped.get("resolved_ip"), "resolved_ip", 0.95),
        ])
        return rec, links, "DNS_QUERY", q_ts, None

    # Default / vpn_proxy
    c_ts, _ = normalize_timestamp(mapped.get("connection_timestamp"), config.UTC)
    if not c_ts:
        raise ValueError("Missing VPN connection timestamp")
    ass_ip, _, _ = normalize_ip(mapped.get("assigned_ip"))
    src_ip, _, _ = normalize_ip(mapped.get("source_ip"))
    acc_id = normalize_identifier(mapped.get("account_id"))
    dur = int(mapped["session_duration_sec"]) if mapped.get("session_duration_sec") and mapped["session_duration_sec"].isdigit() else None
    rec = VPNProxyRecord(
        record_id=rec_id, account_id=acc_id, assigned_ip=ass_ip, source_ip=src_ip,
        connection_timestamp=c_ts, session_duration_sec=dur,
        extra=extra, source_file=fname, source_row=row.row_number,
    )
    links.extend([
        ("IP", ass_ip or "", mapped.get("assigned_ip"), "vpn_assigned_ip", 0.95),
        ("IP", src_ip or "", mapped.get("source_ip"), "vpn_source_ip", 0.95),
        ("OTHER", acc_id or "", mapped.get("account_id"), "vpn_account", 0.90),
    ])
    return rec, links, "VPN_SESSION", c_ts, None


def _process_device_json(
    ev_id: str,
    fname: str,
    payload: dict[str, Any],
    db: ForensicDB,
) -> tuple[int, int, list[RejectedRow], list[ValidationFlag]]:
    device_id = str(payload.get("imei") or payload.get("device_id") or "UNKNOWN_DEVICE")
    rows_in = 0
    ok_count = 0
    rejected: list[RejectedRow] = []
    flags: list[ValidationFlag] = []

    section_map = [
        ("chats", "CHAT"),
        ("sms", "SMS"),
        ("installed_apps", "INSTALLED_APP"),
        ("contacts", "CONTACT"),
        ("call_logs", "CALL_LOG"),
    ]
    for sec_key, art_type in section_map:
        items = payload.get(sec_key)
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items, start=1):
            rows_in += 1
            if not isinstance(item, dict):
                rejected.append(RejectedRow(source_file=fname, source_row=idx, reason="Non-object item in device JSON", raw=item))
                continue
            ts, _ = normalize_timestamp(item.get("timestamp") or item.get("time") or item.get("date"), config.DEVICE["assume_tz"], config.DEVICE["date_formats"])
            dir_raw = str(item.get("direction") or "").upper()
            direction = dir_raw if dir_raw in {"IN", "OUT"} else None
            counterparty = normalize_phone(item.get("counterparty") or item.get("number") or item.get("sender")) or normalize_identifier(item.get("counterparty"))
            extra = {k: v for k, v in item.items() if k not in {"app", "timestamp", "time", "direction", "counterparty", "content", "message", "deleted"}}

            art = DeviceArtifact(
                artifact_id=f"dev_{ev_id}_{sec_key}_{idx}",
                device_id=device_id,
                artifact_type=art_type,  # type: ignore[arg-type]
                app=normalize_identifier(item.get("app") or item.get("app_name")),
                timestamp=ts,
                direction=direction,  # type: ignore[arg-type]
                counterparty=counterparty,
                content=item.get("content") or item.get("message") or item.get("name"),
                deleted=bool(item.get("deleted", False)),
                extra=extra,
                source_file=fname,
                source_row=idx,
            )
            db.execute(
                """
                INSERT INTO device_artifacts
                (evidence_id, artifact_id, device_id, artifact_type, timestamp, counterparty, source_file, source_row, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev_id, art.artifact_id, art.device_id, art.artifact_type,
                    art.timestamp.isoformat() if art.timestamp else None,
                    art.counterparty, art.source_file, art.source_row, art.model_dump_json(),
                ),
            )
            links = [("IMEI", device_id, device_id, "extracted_device", 0.98)]
            if counterparty:
                ent_t = "PHONE" if counterparty.startswith("+") else "OTHER"
                links.append((ent_t, counterparty, counterparty, "counterparty", 0.88))
            _record_event_and_entities(
                db, ev_id, f"evt_{uuid.uuid4().hex[:12]}", f"DEVICE_{art_type}",
                art.timestamp, None, None, "DELETED" if art.deleted else "PRESENT",
                "DeviceArtifact", art.artifact_id, fname, idx, {"app": art.app}, links,
            )
            ok_count += 1

    return rows_in, ok_count, rejected, flags


def _process_unstructured_document(
    ev_id: str,
    fname: str,
    ev_type: str,
    extraction: RawExtraction,
    db: ForensicDB,
) -> tuple[int, int, list[ValidationFlag]]:
    full_text = "\n".join(b.get("text", "") for b in extraction.text_blocks)
    if not full_text.strip():
        return 0, 0, []

    flags: list[ValidationFlag] = []
    extracted_ents = extract_entities_from_text(full_text, fname, source_row=1, page=1)
    rec_id = f"{ev_type[:4]}_{ev_id}_1"
    ent_links: list[tuple[str, str, Optional[str], str, float]] = [
        (e["entity_type"], e["extracted_value"], e["raw_value"], "mentioned_in_document", e["confidence"])
        for e in extracted_ents
    ]

    def _find_first(pattern: str) -> Optional[str]:
        m = re.search(pattern, full_text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    amt_str = _find_first(r"(?:Amount|Rs\.?|INR|₹)\s*[:\-]?\s*([\d,]+(?:\.\d{1,2})?)")
    amt_dec, _ = normalize_amount(amt_str)
    utr = _find_first(r"(?:UTR|RRN|Transaction\s*(?:ID|Ref|Reference))\s*[:\-#]?\s*([A-Za-z0-9]{8,24})")
    ts_str = _find_first(r"(?:Date(?:\s*&\s*Time)?|Timestamp|Incident\s*Date)\s*[:\-]?\s*([0-9/\-:\s]{8,22})")
    ts, _ = normalize_timestamp(ts_str, config.IST)

    if ev_type == "ncrp_complaint":
        ack = _find_first(r"(?:Acknowledgement\s*(?:No|Number)|Complaint\s*ID)\s*[:\-#]?\s*([A-Za-z0-9\-/]+)")
        rec = CyberComplaintRecord(
            record_id=rec_id,
            acknowledgement_no=ack,
            incident_timestamp=ts,
            complaint_description=full_text[:2000],
            utr=utr,
            amount=float(amt_dec) if amt_dec else None,
            suspect_identifiers=[e["extracted_value"] for e in extracted_ents],
            ocr_confidence=extraction.ocr_confidence,
            source_file=fname,
            source_row=1,
        )
        evt_type = "NCRP_COMPLAINT"
    elif ev_type == "fir_complaint":
        fir_no = _find_first(r"(?:FIR\s*(?:No|Number))\s*[:\-#]?\s*([A-Za-z0-9\-/]+)")
        ps = _find_first(r"(?:Police\s*Station|P\.S\.)\s*[:\-]?\s*([^\n,]+)")
        secs = re.findall(r"(?:Section|u/s)\s*([0-9A-Za-z\(\)\s]+?)(?:,|\.|and|\n)", full_text, re.IGNORECASE)
        rec = FIRRecord(
            record_id=rec_id,
            fir_number=fir_no,
            police_station=ps,
            sections_invoked=[s.strip() for s in secs[:15]],
            incident_chronology=full_text[:3000],
            fir_timestamp=ts,
            ocr_confidence=extraction.ocr_confidence,
            source_file=fname,
            source_row=1,
        )
        evt_type = "FIR_COMPLAINT"
    elif ev_type == "bank_kyc":
        pan = _find_first(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")
        ifsc = _find_first(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
        acc = _find_first(r"(?:Account\s*(?:No|Number)|A/c\s*No)\s*[:\-]?\s*(\d{9,18})")
        name = _find_first(r"(?:Name|Account\s*Holder)\s*[:\-]?\s*([A-Za-z\s\.]{3,60})")
        rec = BankKYCRecord(
            record_id=rec_id,
            account_number=acc,
            ifsc=ifsc,
            account_holder_name=name,
            pan=pan,
            ocr_confidence=extraction.ocr_confidence,
            extra={"raw_text_excerpt": full_text[:1500]},
            source_file=fname,
            source_row=1,
        )
        evt_type = "BANK_KYC"
    else:
        kind = "PAYMENT_RECEIPT" if ev_type == "payment_receipt" else "TXN_SCREENSHOT"
        rec = PaymentArtifactRecord(
            record_id=rec_id,
            artifact_kind=kind,  # type: ignore[arg-type]
            txn_id=utr,
            txn_ref=utr,
            amount=float(amt_dec) if amt_dec else None,
            timestamp=ts,
            ocr_confidence=extraction.ocr_confidence,
            extra={"raw_text_excerpt": full_text[:1500]},
            source_file=fname,
            source_row=1,
        )
        evt_type = kind

    db.execute(
        """
        INSERT INTO extended_records
        (evidence_id, record_type, record_id, timestamp, source_file, source_row, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ev_id, ev_type, rec_id, ts.isoformat() if ts else None, fname, 1, rec.model_dump_json()),
    )
    _record_event_and_entities(
        db, ev_id, f"evt_{uuid.uuid4().hex[:12]}", evt_type, ts,
        float(amt_dec) if amt_dec else None, None, None,
        type(rec).__name__, rec_id, fname, 1,
        {"ocr_used": extraction.ocr_used, "ocr_confidence": extraction.ocr_confidence},
        ent_links,
    )
    return 1, 1, flags


def _run_rrn_corroboration(db: ForensicDB) -> None:
    """Links UPI_LOG transactions and BANK_STATEMENT transactions sharing the same RRN."""
    dups = db.fetch_all(
        """
        SELECT rrn, GROUP_CONCAT(DISTINCT source_file) AS files, COUNT(DISTINCT source_type) AS types
        FROM transactions
        WHERE rrn IS NOT NULL AND rrn != ''
        GROUP BY rrn
        HAVING types > 1
        """
    )
    for d in dups:
        rrn = d["rrn"]
        files = [f for f in (d["files"] or "").split(",") if f]
        rows = db.fetch_all("SELECT id, source_file, payload_json FROM transactions WHERE rrn=?", (rrn,))
        for r in rows:
            payload = json.loads(r["payload_json"])
            others = [f for f in files if f != r["source_file"]]
            if sorted(payload.get("corroborated_by", [])) != sorted(others):
                payload["corroborated_by"] = others
                db.execute("UPDATE transactions SET payload_json=? WHERE id=?", (json.dumps(payload), r["id"]))
