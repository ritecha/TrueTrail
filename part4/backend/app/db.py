"""
db.py - Parameterized SQLite persistence layer for normalized forensic evidence,
canonical entities/events/links, review queue, mapping templates, audit/custody logs, and AI logs.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import config


class ForensicDB:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            db_path = config.DATA_DIR / "forensics.db"
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=DELETE;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS evidence_items (
                evidence_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                record_count INTEGER NOT NULL DEFAULT 0,
                rows_in INTEGER NOT NULL DEFAULT 0,
                rejected_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                schema_version TEXT NOT NULL DEFAULT '1.1',
                vault_path TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                case_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_evidence_sha256 ON evidence_items(sha256);

            CREATE TABLE IF NOT EXISTS ingest_jobs (
                job_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                progress_pct INTEGER NOT NULL DEFAULT 0,
                stage TEXT NOT NULL DEFAULT 'INTAKE',
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            -- Append-only chain of custody & audit log
            CREATE TABLE IF NOT EXISTS custody_logs (
                log_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                actor_ip TEXT,
                sha256_at_event TEXT NOT NULL,
                details_json TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS prevent_custody_update
            BEFORE UPDATE ON custody_logs
            BEGIN
                SELECT RAISE(ABORT, 'custody_logs is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS prevent_custody_delete
            BEFORE DELETE ON custody_logs
            BEGIN
                SELECT RAISE(ABORT, 'custody_logs is append-only');
            END;

            -- Canonical v1.1 primary record tables (JSON payload + indexed correlation keys)
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                txn_id TEXT NOT NULL,
                rrn TEXT,
                timestamp TEXT NOT NULL,
                channel TEXT NOT NULL,
                amount REAL NOT NULL,
                direction TEXT,
                sender_account TEXT,
                sender_vpa TEXT,
                receiver_account TEXT,
                receiver_vpa TEXT,
                source_type TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_txn_rrn ON transactions(rrn);
            CREATE INDEX IF NOT EXISTS idx_txn_ts ON transactions(timestamp);

            CREATE TABLE IF NOT EXISTS call_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                record_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                caller TEXT,
                callee TEXT NOT NULL,
                target_number TEXT,
                direction TEXT NOT NULL,
                call_type TEXT NOT NULL,
                imei TEXT,
                imsi TEXT,
                cell_tower_id TEXT,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cdr_caller ON call_records(caller);
            CREATE INDEX IF NOT EXISTS idx_cdr_callee ON call_records(callee);
            CREATE INDEX IF NOT EXISTS idx_cdr_imei ON call_records(imei);

            CREATE TABLE IF NOT EXISTS ip_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                record_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                msisdn TEXT,
                imei TEXT,
                imsi TEXT,
                src_ip TEXT NOT NULL,
                dst_ip TEXT,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ip_src ON ip_sessions(src_ip);
            CREATE INDEX IF NOT EXISTS idx_ip_msisdn ON ip_sessions(msisdn);

            CREATE TABLE IF NOT EXISTS device_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                timestamp TEXT,
                counterparty TEXT,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dev_device ON device_artifacts(device_id);

            -- Extended v1.2 record table for all additional evidence types (KYC, cards, logs, complaints, etc.)
            CREATE TABLE IF NOT EXISTS extended_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                record_type TEXT NOT NULL,
                record_id TEXT NOT NULL,
                timestamp TEXT,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ext_type ON extended_records(record_type);
            CREATE INDEX IF NOT EXISTS idx_ext_ev ON extended_records(evidence_id);

            -- Provenance store (raw, normalized, confidence, source coordinates)
            CREATE TABLE IF NOT EXISTS field_provenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                record_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                raw_value TEXT,
                normalized_value TEXT,
                confidence REAL NOT NULL,
                source_file TEXT NOT NULL,
                source_page INTEGER,
                source_row INTEGER NOT NULL,
                source_column TEXT,
                original_timezone TEXT
            );

            -- Canonical correlation graph: Events, Entities, Links
            CREATE TABLE IF NOT EXISTS normalized_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT,
                amount REAL,
                duration_sec INTEGER,
                status TEXT,
                source_schema TEXT NOT NULL,
                source_record_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                attributes_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts ON normalized_events(timestamp);

            CREATE TABLE IF NOT EXISTS canonical_entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                normalized_value TEXT NOT NULL,
                raw_examples_json TEXT NOT NULL,
                is_private_ip INTEGER,
                ip_version INTEGER,
                UNIQUE(entity_type, normalized_value)
            );
            CREATE INDEX IF NOT EXISTS idx_ent_val ON canonical_entities(normalized_value);

            CREATE TABLE IF NOT EXISTS entity_event_links (
                link_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                role TEXT NOT NULL,
                confidence REAL NOT NULL,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_link_ent ON entity_event_links(entity_id);
            CREATE INDEX IF NOT EXISTS idx_link_evt ON entity_event_links(event_id);

            -- Validation flags, Rejected rows, Review queue, Templates, AI logs
            CREATE TABLE IF NOT EXISTS rejected_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                reason TEXT NOT NULL,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS validation_flags (
                flag_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                message TEXT NOT NULL,
                raw_value TEXT
            );

            CREATE TABLE IF NOT EXISTS review_queue (
                review_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                source_file TEXT NOT NULL,
                column_name TEXT,
                source_row INTEGER NOT NULL DEFAULT 0,
                review_type TEXT NOT NULL,
                candidates_json TEXT NOT NULL,
                sample_values_json TEXT NOT NULL,
                recommended TEXT,
                confidence REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'PENDING',
                resolved_value TEXT,
                reviewer TEXT,
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS mapping_templates (
                template_id TEXT PRIMARY KEY,
                evidence_type TEXT NOT NULL,
                raw_header_norm TEXT NOT NULL,
                target_field TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(evidence_type, raw_header_norm)
            );

            CREATE TABLE IF NOT EXISTS ai_interpretation_logs (
                log_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                task TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                temperature REAL NOT NULL,
                prompt_hash TEXT NOT NULL,
                input_summary TEXT NOT NULL,
                output_json TEXT NOT NULL,
                deterministic_verified INTEGER NOT NULL,
                verification_notes TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_canonical_entity(
        self,
        entity_id: str,
        entity_type: str,
        normalized_value: str,
        raw_example: str,
        is_private_ip: Optional[bool] = None,
        ip_version: Optional[int] = None,
    ) -> str:
        with self._lock:
            existing = self._conn.execute(
                "SELECT entity_id, raw_examples_json FROM canonical_entities WHERE entity_type=? AND normalized_value=?",
                (entity_type, normalized_value),
            ).fetchone()
            if existing:
                examples = json.loads(existing["raw_examples_json"])
                if raw_example and raw_example not in examples and len(examples) < 10:
                    examples.append(raw_example)
                    self._conn.execute(
                        "UPDATE canonical_entities SET raw_examples_json=? WHERE entity_id=?",
                        (json.dumps(examples), existing["entity_id"]),
                    )
                    self._conn.commit()
                return existing["entity_id"]
            examples = [raw_example] if raw_example else []
            self._conn.execute(
                """
                INSERT INTO canonical_entities
                (entity_id, entity_type, normalized_value, raw_examples_json, is_private_ip, ip_version)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    entity_type,
                    normalized_value,
                    json.dumps(examples),
                    1 if is_private_ip else (0 if is_private_ip is False else None),
                    ip_version,
                ),
            )
            self._conn.commit()
            return entity_id

    def append_custody_log(
        self,
        log_id: str,
        evidence_id: str,
        action: str,
        actor: str,
        sha256_at_event: str,
        details: dict[str, Any],
        actor_ip: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        self.execute(
            """
            INSERT INTO custody_logs
            (log_id, evidence_id, action, actor, actor_ip, sha256_at_event, details_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (log_id, evidence_id, action, actor, actor_ip, sha256_at_event, json.dumps(details, default=str), ts),
        )


_DB_INSTANCE: Optional[ForensicDB] = None


def get_db() -> ForensicDB:
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        _DB_INSTANCE = ForensicDB()
    return _DB_INSTANCE
