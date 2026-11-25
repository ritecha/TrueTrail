"""
mapper.py - Stage 5: 6-Rung Header & Field Mapping Ladder.

Rung 0: Saved human-confirmed templates for this evidence type
Rung 1: Alias dictionary (normalized lowercase alphanumeric)
Rung 2: Fuzzy matching (rapidfuzz if available, else difflib)
Rung 3: Content-based pattern/validity detection (amounts, dates, IFSC, VPA, IP, IMEI, card, phone)
Rung 4: Neighbouring column context & structural relationships (debit/credit/balance, caller/callee)
Rung 5: AI suggestion (strictly from allowed target fields, logged & rule-checked)
Rung 6: Human review queue (ReviewItem emitted when confidence is low or ambiguous)

Unrecognized columns are NEVER discarded — they are preserved in extra/additional_fields.
"""
from __future__ import annotations

import difflib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import config
from app import ai_service
from app.db import ForensicDB
from app.disambiguator import disambiguate_numeric_column, luhn_valid
from app.extractors.base import ExtractedTable


@dataclass
class ColumnDecision:
    raw_header: str
    target_field: Optional[str]     # None -> keep as unmapped extra field
    confidence: float
    rung_used: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    needs_review: bool = False


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", h.lower())


def _fuzzy_ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz
        return fuzz.token_sort_ratio(a, b) / 100.0
    except ImportError:
        return difflib.SequenceMatcher(None, a, b).ratio()


def get_profile_columns(evidence_type: str) -> dict[str, list[str]]:
    if evidence_type == "upi":
        return config.UPI["columns"]
    if evidence_type == "cdr":
        return config.CDR["columns"]
    if evidence_type == "ipdr":
        return config.IPDR["columns"]
    if evidence_type == "bank_statement":
        return config.BANK_PROFILES["default"]["columns"]
    if evidence_type in config.EXTENDED_EVIDENCE_PROFILES:
        return config.EXTENDED_EVIDENCE_PROFILES[evidence_type]["columns"]
    return {}


def _detect_by_content(
    header: str,
    sample_values: list[str],
    evidence_type: str,
    neighbour_headers: list[str],
    allowed_fields: list[str],
) -> tuple[Optional[str], float, list[dict[str, Any]]]:
    non_empty = [v.strip() for v in sample_values if v and v.strip()]
    if not non_empty:
        return None, 0.0, []

    n = len(non_empty)
    vpa_r = sum(1 for v in non_empty if re.match(config.REGEX_PATTERNS["vpa"], v)) / n
    ifsc_r = sum(1 for v in non_empty if re.match(config.REGEX_PATTERNS["ifsc"], v.upper())) / n
    ip_r = sum(1 for v in non_empty if re.match(config.REGEX_PATTERNS["ipv4"], v)) / n
    card_r = sum(1 for v in non_empty if re.match(config.REGEX_PATTERNS["masked_card"], v)) / n
    pan_r = sum(1 for v in non_empty if re.match(config.REGEX_PATTERNS["pan"], v.upper())) / n
    imei_r = sum(1 for v in non_empty if re.match(r"^\d{15}$", v) and luhn_valid(v)) / n
    date_r = sum(1 for v in non_empty if re.search(r"\d{2,4}[-/]\d{1,2}[-/]\d{2,4}", v)) / n

    if vpa_r >= 0.6:
        for cand in ("payer_vpa", "payee_vpa"):
            if cand in allowed_fields:
                return cand, round(0.75 * vpa_r, 3), [{"field": cand, "score": round(0.75 * vpa_r, 3)}]
    if ifsc_r >= 0.6:
        for cand in ("ifsc", "receiver_ifsc", "sender_ifsc", "payer_ifsc", "payee_ifsc"):
            if cand in allowed_fields:
                return cand, round(0.86 * ifsc_r, 3), [{"field": cand, "score": round(0.86 * ifsc_r, 3)}]
    if ip_r >= 0.7:
        for cand in ("public_ip", "source_ip", "ip", "assigned_ip", "resolved_ip"):
            if cand in allowed_fields:
                return cand, round(0.82 * ip_r, 3), [{"field": cand, "score": round(0.82 * ip_r, 3)}]
    if card_r >= 0.6 and "masked_card_number" in allowed_fields:
        return "masked_card_number", round(0.88 * card_r, 3), [{"field": "masked_card_number", "score": 0.88}]
    if pan_r >= 0.6 and "pan" in allowed_fields:
        return "pan", round(0.90 * pan_r, 3), [{"field": "pan", "score": 0.90}]
    if imei_r >= 0.6 and "imei" in allowed_fields:
        return "imei", round(0.88 * imei_r, 3), [{"field": "imei", "score": 0.88}]
    if date_r >= 0.7:
        for cand in ("timestamp", "txn_date", "start", "login_timestamp", "query_timestamp", "session_start"):
            if cand in allowed_fields:
                return cand, round(0.78 * date_r, 3), [{"field": cand, "score": round(0.78 * date_r, 3)}]

    # Numeric disambiguation ("9087772990" problem)
    disambig = disambiguate_numeric_column(header, non_empty, evidence_type, neighbour_headers)
    if disambig.resolved_type == "AMBIGUOUS":
        return None, disambig.confidence, disambig.candidates
    if disambig.resolved_type == "AMOUNT":
        for cand in ("amount", "debit", "credit"):
            if cand in allowed_fields:
                return cand, disambig.confidence, disambig.candidates
    if disambig.resolved_type == "PHONE":
        for cand in ("msisdn", "registered_mobile", "mobile_number", "calling", "called", "payer_mobile"):
            if cand in allowed_fields:
                return cand, disambig.confidence, disambig.candidates
    if disambig.resolved_type == "UTR":
        for cand in ("rrn", "ref_no", "txn_ref"):
            if cand in allowed_fields:
                return cand, disambig.confidence, disambig.candidates
    if disambig.resolved_type == "ACCOUNT":
        for cand in ("account_number", "sender_account", "receiver_account", "payer_account", "payee_account"):
            if cand in allowed_fields:
                return cand, disambig.confidence, disambig.candidates

    return None, 0.0, disambig.candidates


def map_table_columns(
    table: ExtractedTable,
    evidence_type: str,
    evidence_id: str,
    source_file: str,
    db: ForensicDB,
) -> tuple[dict[str, ColumnDecision], list[dict[str, Any]]]:
    """
    Maps raw table headers -> canonical fields using the 6-rung ladder.
    Returns (decisions_by_raw_header, review_items_created).
    """
    profile_cols = get_profile_columns(evidence_type)
    allowed_fields = list(profile_cols.keys())

    # Load saved human-confirmed templates (Rung 0)
    template_rows = db.fetch_all(
        "SELECT raw_header_norm, target_field FROM mapping_templates WHERE evidence_type=?",
        (evidence_type,),
    )
    saved_templates = {r["raw_header_norm"]: r["target_field"] for r in template_rows}

    # Build exact normalized alias lookup (Rung 1)
    alias_lookup: dict[str, str] = {}
    for canonical, aliases in profile_cols.items():
        alias_lookup[_norm_header(canonical)] = canonical
        for a in aliases:
            alias_lookup[_norm_header(a)] = canonical

    decisions: dict[str, ColumnDecision] = {}
    used_targets: set[str] = set()
    review_items: list[dict[str, Any]] = []

    for col_idx, raw_hdr in enumerate(table.headers):
        norm_h = _norm_header(raw_hdr)
        samples = [r.values.get(raw_hdr, "") for r in table.rows[:25] if r.values.get(raw_hdr, "").strip()]
        neighbours = [h for i, h in enumerate(table.headers) if abs(i - col_idx) <= 2 and i != col_idx]

        # Rung 0: Saved template
        if norm_h in saved_templates and saved_templates[norm_h] not in used_targets:
            tgt = saved_templates[norm_h]
            used_targets.add(tgt)
            decisions[raw_hdr] = ColumnDecision(raw_hdr, tgt, 0.99, "rung0_saved_template")
            continue

        # Rung 1: Exact alias dictionary
        if norm_h in alias_lookup and alias_lookup[norm_h] not in used_targets:
            tgt = alias_lookup[norm_h]
            used_targets.add(tgt)
            decisions[raw_hdr] = ColumnDecision(raw_hdr, tgt, 0.96, "rung1_alias")
            continue

        # Rung 2: Fuzzy header match
        best_fuzzy_target: Optional[str] = None
        best_fuzzy_score = 0.0
        for canonical, aliases in profile_cols.items():
            if canonical in used_targets:
                continue
            for candidate_alias in [canonical, *aliases]:
                score = _fuzzy_ratio(raw_hdr.lower(), candidate_alias.lower())
                if score > best_fuzzy_score:
                    best_fuzzy_score = score
                    best_fuzzy_target = canonical
        if best_fuzzy_target and best_fuzzy_score >= 0.84:
            used_targets.add(best_fuzzy_target)
            decisions[raw_hdr] = ColumnDecision(raw_hdr, best_fuzzy_target, round(best_fuzzy_score, 3), "rung2_fuzzy")
            continue

        # Rung 3 & 4: Content-based & context detection
        content_target, content_conf, candidates = _detect_by_content(
            raw_hdr, samples, evidence_type, neighbours, [f for f in allowed_fields if f not in used_targets]
        )
        # Rung 4 structural heuristic for bank statements: alternating empty debit/credit followed by balance
        if evidence_type == "bank_statement" and content_target in {"amount", "debit", "credit"}:
            if any(k in raw_hdr.lower() for k in ("dr", "debit", "withdrawal")):
                content_target = "debit"
            elif any(k in raw_hdr.lower() for k in ("cr", "credit", "deposit")):
                content_target = "credit"

        if content_target and content_target not in used_targets and content_conf >= config.MAPPING_ACCEPT_THRESHOLD:
            used_targets.add(content_target)
            decisions[raw_hdr] = ColumnDecision(raw_hdr, content_target, content_conf, "rung3_4_content_context", candidates)
            continue

        # Rung 5: AI suggestion (strictly constrained & logged)
        ai_target, ai_conf = ai_service.suggest_column_mapping(
            db=db,
            evidence_id=evidence_id,
            header=raw_hdr,
            sample_values=samples[:5],
            allowed_fields=[f for f in allowed_fields if f not in used_targets],
        )
        if ai_target and ai_conf >= config.MAPPING_ACCEPT_THRESHOLD:
            used_targets.add(ai_target)
            decisions[raw_hdr] = ColumnDecision(raw_hdr, ai_target, ai_conf, "rung5_ai_verified", candidates)
            continue

        # Rung 6: Queue for human review if plausible partial candidates exist, else preserve as extra
        recommended = ai_target or content_target or (best_fuzzy_target if best_fuzzy_score >= 0.55 else None)
        best_conf = max(content_conf, ai_conf, round(best_fuzzy_score, 3) if best_fuzzy_target else 0.0)
        needs_review = bool(samples) and (
            best_conf >= config.MAPPING_REVIEW_THRESHOLD
            or (candidates and any(c.get("type") for c in candidates))
        )

        if needs_review:
            review_id = f"rev_{uuid.uuid4().hex[:12]}"
            review_type = "AMBIGUOUS_ENTITY" if (candidates and not content_target) else "COLUMN_MAPPING"
            cand_payload = candidates or (
                [{"field": recommended, "score": best_conf}] if recommended else []
            )
            db.execute(
                """
                INSERT INTO review_queue
                (review_id, evidence_id, source_file, column_name, source_row, review_type,
                 candidates_json, sample_values_json, recommended, confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    review_id,
                    evidence_id,
                    source_file,
                    raw_hdr,
                    0,
                    review_type,
                    _json_dumps(cand_payload),
                    _json_dumps(samples[:5]),
                    recommended,
                    best_conf,
                ),
            )
            review_items.append({
                "review_id": review_id,
                "column_name": raw_hdr,
                "review_type": review_type,
                "recommended": recommended,
                "confidence": best_conf,
            })

        # Unmapped columns stay preserved in extra/additional_fields; never discarded
        decisions[raw_hdr] = ColumnDecision(
            raw_header=raw_hdr,
            target_field=recommended if (recommended and best_conf >= 0.60 and recommended not in used_targets) else None,
            confidence=best_conf,
            rung_used="rung6_review_queued" if needs_review else "unmapped_extra",
            candidates=candidates,
            needs_review=needs_review,
        )
        if decisions[raw_hdr].target_field:
            used_targets.add(decisions[raw_hdr].target_field)

    return decisions, review_items


def _json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
