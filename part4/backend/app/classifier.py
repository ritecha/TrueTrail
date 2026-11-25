"""
classifier.py - Stage 4: Multi-signal weighted evidence classifier across all 21 sources.
Combines header keywords, column patterns, title/issuer text, JSON keys, and value regex signals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import config
from app.extractors.base import RawExtraction


@dataclass
class ClassificationResult:
    evidence_type: str
    confidence: float
    signals: dict[str, float]


_CLASSIFIER_RULES: dict[str, dict[str, Any]] = {
    "upi": {
        "headers": ["payer_vpa", "payee_vpa", "rrn", "txn_id", "response_code", "psp app", "app_name", "upi ref"],
        "text_keywords": ["payer vpa", "payee vpa", "upi transaction", "npci", "psp"],
        "value_patterns": [config.REGEX_PATTERNS["vpa"]],
    },
    "bank_statement": {
        "headers": ["narration", "withdrawal", "deposit", "closing balance", "balance", "chq/ref no", "value date", "dr amount", "cr amount"],
        "text_keywords": ["statement of account", "opening balance", "closing balance", "ifsc", "account no"],
        "value_patterns": [config.REGEX_PATTERNS["ifsc"]],
    },
    "interbank_transfer": {
        "headers": ["remitter account", "beneficiary account", "utr", "remitter ifsc", "beneficiary ifsc", "transfer type"],
        "text_keywords": ["neft", "rtgs", "imps", "interbank", "utr"],
        "value_patterns": [config.REGEX_PATTERNS["ifsc"]],
    },
    "card_transaction": {
        "headers": ["masked card", "card number", "merchant id", "terminal id", "acquiring bank", "auth code", "authorization code"],
        "text_keywords": ["card transaction", "pos", "terminal id", "acquiring bank"],
        "value_patterns": [config.REGEX_PATTERNS["masked_card"]],
    },
    "internet_banking_log": {
        "headers": ["login timestamp", "source ip", "session id", "user agent", "browser", "authentication event", "auth event"],
        "text_keywords": ["internet banking", "netbanking", "login session", "user agent"],
        "value_patterns": [config.REGEX_PATTERNS["ipv4"]],
    },
    "mobile_banking_log": {
        "headers": ["app version", "device id", "registered mobile", "login time", "session id"],
        "text_keywords": ["mobile banking", "app version", "device fingerprint"],
        "value_patterns": [config.REGEX_PATTERNS["ipv4"]],
    },
    "wallet_record": {
        "headers": ["wallet id", "ppi id", "linked bank account", "kyc level", "kyc details"],
        "text_keywords": ["payment wallet", "ppi", "wallet id", "linked bank"],
        "value_patterns": [],
    },
    "bank_kyc": {
        "headers": ["account holder name", "pan", "masked aadhaar", "account opening date", "dob", "kyc verification"],
        "text_keywords": ["kyc", "account opening", "know your customer", "pan card", "aadhaar", "date of birth"],
        "value_patterns": [config.REGEX_PATTERNS["pan"], config.REGEX_PATTERNS["masked_aadhaar"]],
    },
    "cdr": {
        "headers": ["calling_no", "called_no", "a_party", "b_party", "call_type", "duration_sec", "first_cell_id", "imei", "imsi", "lac"],
        "text_keywords": ["call detail record", "moc", "mtc", "sms-mo", "sms-mt", "a party", "b party"],
        "value_patterns": [config.REGEX_PATTERNS["imei"], config.REGEX_PATTERNS["imsi_india"]],
    },
    "ipdr": {
        "headers": ["public_ip", "private_ip", "dst_ip", "dst_port", "src_port", "uplink_bytes", "downlink_bytes", "apn", "msisdn"],
        "text_keywords": ["ipdr", "uplink", "downlink", "apn", "session start"],
        "value_patterns": [config.REGEX_PATTERNS["ipv4"]],
    },
    "cell_tower": {
        "headers": ["cell_id", "cell id", "sector id", "tower_lat", "tower_lon", "tower address", "site address"],
        "text_keywords": ["cell tower", "sector id", "tower coordinates", "azimuth"],
        "value_patterns": [],
    },
    "sim_swap": {
        "headers": ["old imsi", "new imsi", "sim activation time", "replacement request time", "request channel"],
        "text_keywords": ["sim swap", "sim change", "sim replacement", "old imsi", "new imsi"],
        "value_patterns": [config.REGEX_PATTERNS["imsi_india"]],
    },
    "sms_record": {
        "headers": ["sender number", "receiver number", "message delivery status", "message id", "sms category"],
        "text_keywords": ["sms delivery", "message id", "sms category", "smsc"],
        "value_patterns": [],
    },
    "isp_subscriber": {
        "headers": ["subscriber name", "registered address", "ip allocation details", "connection start", "connection end", "assigned ip"],
        "text_keywords": ["isp subscriber", "broadband", "installation address", "static ip"],
        "value_patterns": [config.REGEX_PATTERNS["ipv4"]],
    },
    "ip_allocation": {
        "headers": ["public ip", "private ip", "port number", "subscriber id", "session start", "session end", "timezone"],
        "text_keywords": ["ip allocation", "nat log", "cgnat", "session log"],
        "value_patterns": [config.REGEX_PATTERNS["ipv4"]],
    },
    "dns_record": {
        "headers": ["domain", "queried hostname", "resolved ip", "query timestamp", "record type", "qname", "qtype"],
        "text_keywords": ["dns query", "resolved ip", "cname", "nxdomain", "a record"],
        "value_patterns": [config.REGEX_PATTERNS["domain"]],
    },
    "vpn_proxy": {
        "headers": ["account id", "assigned ip", "source ip", "connection timestamp", "session duration"],
        "text_keywords": ["vpn", "proxy", "wireguard", "openvpn", "tunnel"],
        "value_patterns": [config.REGEX_PATTERNS["ipv4"]],
    },
    "ncrp_complaint": {
        "headers": ["acknowledgement number", "complaint description", "victim details", "suspect identifiers"],
        "text_keywords": ["national cyber crime", "ncrp", "cybercrime.gov.in", "acknowledgement no", "acknowledgement number", "fraudulent transaction"],
        "value_patterns": [],
    },
    "fir_complaint": {
        "headers": ["fir number", "police station", "sections invoked", "complainant details", "accused details"],
        "text_keywords": ["first information report", "fir no", "police station", "bns", "ipc", "section 66", "complainant", "accused"],
        "value_patterns": [],
    },
    "txn_screenshot": {
        "headers": [],
        "text_keywords": ["paid to", "debited from", "upi transaction id", "google pay", "phonepe", "paytm", "bhim", "completed", "utr"],
        "value_patterns": [config.REGEX_PATTERNS["vpa"], config.REGEX_PATTERNS["rrn"]],
    },
    "payment_receipt": {
        "headers": [],
        "text_keywords": ["payment receipt", "merchant id", "invoice", "receipt no", "transaction reference", "authorized"],
        "value_patterns": [],
    },
}


def classify_evidence(
    extraction: RawExtraction,
    filename: str = "",
    hint_type: str | None = None,
) -> ClassificationResult:
    # Fast path for Cellebrite-style nested device forensics JSON
    if extraction.source_format == "json" and isinstance(extraction.json_payload, dict):
        payload = extraction.json_payload
        device_keys = {"chats", "sms", "installed_apps", "contacts", "call_logs", "device_info", "imei"}
        if device_keys.intersection(payload.keys()):
            return ClassificationResult(
                evidence_type="device",
                confidence=0.96,
                signals={"device_json_keys": 0.96},
            )

    headers_norm = " ".join(
        h.lower().strip()
        for t in extraction.tables
        for h in t.headers
    )
    meta_text = " ".join(
        ln.lower()
        for t in extraction.tables
        for ln in t.metadata_lines
    )
    block_text = " ".join(b.get("text", "").lower() for b in extraction.text_blocks[:5])
    combined_text = f"{filename.lower()} {meta_text} {block_text}"

    sample_vals: list[str] = []
    for t in extraction.tables[:2]:
        for row in t.rows[:15]:
            sample_vals.extend(v for v in row.values.values() if v)
    sample_vals = sample_vals[:120]

    scores: dict[str, float] = {}
    for ev_type, rules in _CLASSIFIER_RULES.items():
        score = 0.0
        for h_kw in rules["headers"]:
            if h_kw in headers_norm:
                score += 1.2
        for t_kw in rules["text_keywords"]:
            if t_kw in combined_text:
                score += 1.0
        for pat in rules["value_patterns"]:
            matches = sum(1 for v in sample_vals if re.match(pat, v.strip()))
            if matches >= 2:
                score += 1.1
        if filename and ev_type.replace("_", " ") in filename.lower().replace("_", " "):
            score += 0.8
        if hint_type and hint_type == ev_type:
            score += 0.5

        # Distinguish screenshot/receipt images vs tabular exports
        if extraction.source_format in {"image", "scanned_pdf"} and ev_type in {
            "ncrp_complaint", "fir_complaint", "bank_kyc", "txn_screenshot", "payment_receipt"
        }:
            score += 0.4

        scores[ev_type] = round(score, 3)

    best_type = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]
    total_top = sum(sorted(scores.values(), reverse=True)[:3]) or 1.0
    confidence = round(min(0.99, best_score / max(total_top, 3.0)), 3)

    if best_score == 0.0:
        if extraction.source_format in {"image", "scanned_pdf"}:
            best_type = "txn_screenshot"
            confidence = 0.35
        elif hint_type:
            best_type = hint_type
            confidence = 0.45
        else:
            best_type = "bank_statement" if extraction.tables else "ncrp_complaint"
            confidence = 0.25

    return ClassificationResult(evidence_type=best_type, confidence=confidence, signals=scores)
