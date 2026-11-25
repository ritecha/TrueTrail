"""
disambiguator.py - Section 4:
1. Solves the "9087772990" problem at the column level (combining header clues, source type,
   digit/prefix statistics, repetition, Luhn/IMSI validity, and neighbouring columns).
   When top two interpretations are too close, marks ambiguous for human review.
2. Unstructured text entity extraction (UPI narrations, FIRs, NCRP complaints, OCR receipts).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

import config


@dataclass
class DisambiguationResult:
    resolved_type: str              # PHONE | ACCOUNT | AMOUNT | UTR | IMEI | IMSI | AMBIGUOUS
    confidence: float
    candidates: list[dict[str, float | str]]
    is_ambiguous: bool


def luhn_valid(digits: str) -> bool:
    if not digits.isdigit():
        return False
    total = 0
    reverse_digits = digits[::-1]
    for idx, ch in enumerate(reverse_digits):
        d = int(ch)
        if idx % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def disambiguate_numeric_column(
    header: str,
    values: list[str],
    evidence_type: str,
    neighbour_headers: list[str],
) -> DisambiguationResult:
    non_empty = [v.strip() for v in values if v and v.strip()]
    if not non_empty:
        return DisambiguationResult("UNKNOWN", 0.0, [], False)

    scores: dict[str, float] = {
        "PHONE": 0.0,
        "AMOUNT": 0.0,
        "ACCOUNT": 0.0,
        "UTR": 0.0,
        "IMEI": 0.0,
        "IMSI": 0.0,
    }
    hdr_l = header.lower()
    neigh_l = " ".join(h.lower() for h in neighbour_headers)

    # Signal 1: Header clues
    if any(k in hdr_l for k in ("phone", "mobile", "msisdn", "calling", "called", "party", "contact")):
        scores["PHONE"] += 0.38
    if any(k in hdr_l for k in ("amt", "amount", "rupees", "inr", "debit", "credit", "balance", "withdrawal", "deposit")):
        scores["AMOUNT"] += 0.42
    if any(k in hdr_l for k in ("account", "acct", "a/c")):
        scores["ACCOUNT"] += 0.40
    if any(k in hdr_l for k in ("utr", "rrn", "ref")):
        scores["UTR"] += 0.40
    if "imei" in hdr_l:
        scores["IMEI"] += 0.45
    if "imsi" in hdr_l:
        scores["IMSI"] += 0.45

    # Signal 2: Evidence source context
    if evidence_type in {"cdr", "ipdr", "sms_record", "sim_swap", "cell_tower"}:
        scores["PHONE"] += 0.18
        scores["IMEI"] += 0.08
        scores["IMSI"] += 0.08
    elif evidence_type in {"bank_statement", "upi", "interbank_transfer", "card_transaction", "wallet_record"}:
        scores["AMOUNT"] += 0.12
        scores["ACCOUNT"] += 0.10
        scores["UTR"] += 0.08

    # Signal 3: Neighbour context
    if any(k in neigh_l for k in ("duration", "call_type", "cell", "lac")):
        scores["PHONE"] += 0.15
    if any(k in neigh_l for k in ("balance", "narration", "ifsc", "debit", "credit")):
        scores["AMOUNT"] += 0.12

    # Signal 4: Column statistics & validity tests
    digits_only = [re.sub(r"^\+91", "", re.sub(r"[\s\-]", "", v)) for v in non_empty]
    indian_mob_ratio = sum(1 for d in digits_only if re.fullmatch(r"(?:91|0)?[6-9]\d{9}", d)) / len(non_empty)
    decimal_comma_ratio = sum(1 for v in non_empty if ("," in v or "." in v) and re.match(config.REGEX_PATTERNS["amount_indian"], v)) / len(non_empty)
    twelve_digit_ratio = sum(1 for d in digits_only if re.fullmatch(r"\d{12}", d)) / len(non_empty)
    imei_ratio = sum(1 for d in digits_only if len(d) == 15 and luhn_valid(d)) / len(non_empty)
    imsi_ratio = sum(1 for d in digits_only if re.fullmatch(r"40[45]\d{12}", d)) / len(non_empty)
    varying_len = len({len(d) for d in digits_only}) > 2

    scores["PHONE"] += indian_mob_ratio * 0.40
    scores["AMOUNT"] += decimal_comma_ratio * 0.42 + (0.12 if varying_len else 0.0)
    scores["UTR"] += twelve_digit_ratio * 0.40
    scores["IMEI"] += imei_ratio * 0.45
    scores["IMSI"] += imsi_ratio * 0.45

    # Signal 5: Plausibility guard (a 10-digit Indian phone number as INR would be > 6 billion)
    numeric_vals = []
    for v in non_empty[:30]:
        cleaned = re.sub(r"[^\d.]", "", v)
        if cleaned and cleaned.count(".") <= 1:
            try:
                numeric_vals.append(float(cleaned))
            except ValueError:
                pass
    if numeric_vals and all(x >= 6_000_000_000 for x in numeric_vals) and indian_mob_ratio > 0.7:
        scores["AMOUNT"] -= 0.35

    # Signal 6: Repetition (same number appearing repeatedly in CDR/transactions -> identifier)
    counts = Counter(digits_only)
    if len(non_empty) >= 4 and max(counts.values()) >= 2:
        scores["PHONE"] += 0.06
        scores["ACCOUNT"] += 0.05

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_label, top_score = ranked[0]
    second_label, second_score = ranked[1]
    margin = top_score - second_score

    candidates = [{"type": k, "score": round(v, 3)} for k, v in ranked[:3] if v > 0.1]
    is_ambiguous = (top_score < 0.45) or (margin < config.DISAMBIGUATION_MARGIN and second_score > 0.25)

    return DisambiguationResult(
        resolved_type="AMBIGUOUS" if is_ambiguous else top_label,
        confidence=round(min(0.99, max(0.0, top_score)), 3),
        candidates=candidates,
        is_ambiguous=is_ambiguous,
    )


def extract_entities_from_text(
    text: str,
    source_file: str,
    source_row: int = 0,
    page: Optional[int] = None,
) -> list[dict]:
    """
    Extracts candidate forensic identifiers from free text (UPI narrations,
    NCRP complaints, FIRs, SMS/chat contents, OCR text) with exact offset provenance.
    """
    if not text:
        return []

    patterns: list[tuple[str, str, float]] = [
        ("VPA", r"\b[a-zA-Z0-9._\-]{2,}@[a-zA-Z]{2,}[a-zA-Z0-9]*\b", 0.92),
        ("IFSC", r"\b[A-Z]{4}0[A-Z0-9]{6}\b", 0.95),
        ("PAN", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", 0.94),
        ("IP", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b", 0.93),
        ("PHONE", r"(?<!\d)(?:\+91[\-\s]?|91[\-\s]?|0)?([6-9]\d{9})(?!\d)", 0.85),
        ("IMEI", r"(?<!\d)(\d{15})(?!\d)", 0.80),
        ("UTR", r"(?<!\d)(\d{12})(?!\d)", 0.82),
        ("ACCOUNT", r"(?<!\d)(\d{9,18})(?!\d)", 0.55),
    ]

    found: list[dict] = []
    seen_spans: set[tuple[str, str]] = set()

    for ent_type, pat, base_conf in patterns:
        for m in re.finditer(pat, text):
            raw_val = m.group(0).strip()
            val = m.group(1) if m.lastindex else raw_val
            if ent_type == "IMEI" and not luhn_valid(val):
                continue
            if ent_type == "VPA" and val.lower().endswith((".com", ".in", ".org", ".net")):
                # Email rather than VPA
                ent_type_eff = "EMAIL"
            else:
                ent_type_eff = ent_type

            key = (ent_type_eff, val)
            if key in seen_spans:
                continue
            seen_spans.add(key)
            found.append({
                "entity_type": ent_type_eff,
                "raw_value": raw_val,
                "extracted_value": val,
                "confidence": base_conf,
                "span_start": m.start(),
                "span_end": m.end(),
                "source_file": source_file,
                "source_row": source_row,
                "page": page,
            })

    return found
