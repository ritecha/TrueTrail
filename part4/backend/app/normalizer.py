"""
normalizer.py - Stage 6: Canonical normalization rules.
- Time: UTC ISO-8601 (timezone-aware), keeping original text & original timezone
- Money: exact Decimal parsing for Indian commas (1,25,000.00) and Dr/Cr suffixes
- Phone: +91XXXXXXXXXX (E.164)
- IDs (accounts, UTRs, IMEIs): always string, preserving leading zeros
- IPs: IPv4/IPv6 standard string + public/private classification
- Names/Addresses: cleaned comparison key while keeping raw text
"""
from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

import config


_TZ_SUFFIX_RE = re.compile(r"\(UTC\s*([+-]\d{1,2})(?::(\d{2}))?\)\s*$", re.IGNORECASE)


def normalize_timestamp(
    raw: Optional[str | int | float],
    assume_tz: timezone = config.IST,
    extra_formats: Optional[list[str]] = None,
) -> tuple[Optional[datetime], Optional[str]]:
    """
    Returns (utc_datetime, original_timezone_label).
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None

    # Epoch seconds / milliseconds
    if re.fullmatch(r"\d{10}(?:\.\d+)?", text):
        dt = datetime.fromtimestamp(float(text), tz=timezone.utc)
        return dt, "UTC_EPOCH"
    if re.fullmatch(r"\d{13}", text):
        dt = datetime.fromtimestamp(int(text) / 1000.0, tz=timezone.utc)
        return dt, "UTC_EPOCH_MS"

    orig_tz_label = "IST" if assume_tz == config.IST else ("UTC" if assume_tz == config.UTC else str(assume_tz))
    effective_tz = assume_tz

    # Handle explicit "(UTC+5:30)" suffix from Cellebrite/device logs
    m_tz = _TZ_SUFFIX_RE.search(text)
    if m_tz:
        hours = int(m_tz.group(1))
        mins = int(m_tz.group(2) or 0)
        if hours < 0:
            mins = -mins
        effective_tz = timezone(timedelta(hours=hours, minutes=mins))
        orig_tz_label = m_tz.group(0).strip("() ")
        text = text[: m_tz.start()].strip()
    elif text.upper().endswith(" IST"):
        effective_tz = config.IST
        orig_tz_label = "IST"
        text = text[:-4].strip()
    elif text.upper().endswith(" UTC"):
        effective_tz = config.UTC
        orig_tz_label = "UTC"
        text = text[:-4].strip()

    # ISO-8601 native
    iso_candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=effective_tz)
        else:
            orig_tz_label = str(dt.tzinfo)
        return dt.astimezone(timezone.utc), orig_tz_label
    except ValueError:
        pass

    formats = list(extra_formats or []) + config.COMMON_DATE_FORMATS
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            dt = dt.replace(tzinfo=effective_tz)
            return dt.astimezone(timezone.utc), orig_tz_label
        except ValueError:
            continue

    return None, orig_tz_label


def normalize_amount(raw: Optional[str | int | float]) -> tuple[Optional[Decimal], Optional[str]]:
    """
    Parses Indian formatted amounts like '1,25,000.00 Dr', '₹ 45,000', '(500.00)'.
    Returns (positive Decimal amount, inferred_direction 'DEBIT'|'CREDIT'|None).
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text or text in {"-", "--", "NA", "N/A", "null", "None"}:
        return None, None

    direction: Optional[str] = None
    upper = text.upper()
    if re.search(r"\bDR\b", upper) or text.startswith("-") or (text.startswith("(") and text.endswith(")")):
        direction = "DEBIT"
    elif re.search(r"\bCR\b", upper):
        direction = "CREDIT"

    cleaned = re.sub(r"(?i)\b(?:INR|RS\.?|DR|CR)\b|[₹$,\s()]", "", text)
    cleaned = cleaned.lstrip("+-")
    if not cleaned:
        return None, direction

    try:
        val = Decimal(cleaned)
        return abs(val), direction
    except InvalidOperation:
        return None, direction


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"hidden", "private", "anonymous", "unknown", "restricted"}:
        return None
    digits = re.sub(r"[^\d+]", "", text)
    if digits.startswith("+"):
        return digits if len(digits) >= 10 else None
    only_digits = re.sub(r"\D", "", text)
    # Handle 10-digit Indian mobile, 0XXXXXXXXXX, 91XXXXXXXXXX
    if len(only_digits) == 10 and only_digits[0] in "6789":
        return f"+91{only_digits}"
    if len(only_digits) == 11 and only_digits.startswith("0") and only_digits[1] in "6789":
        return f"+91{only_digits[1:]}"
    if len(only_digits) == 12 and only_digits.startswith("91") and only_digits[2] in "6789":
        return f"+{only_digits}"
    # Fallback for landline/shortcodes
    return f"+{only_digits}" if len(only_digits) >= 11 else (only_digits or None)


def normalize_identifier(raw: Optional[str]) -> Optional[str]:
    """Preserves leading zeros and keeps identifier strictly as text."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"na", "n/a", "none", "null", "-"}:
        return None
    return s


def normalize_ip(raw: Optional[str]) -> tuple[Optional[str], Optional[bool], Optional[int]]:
    """
    Returns (normalized_ip_str, is_private, ip_version).
    """
    if not raw:
        return None, None, None
    s = str(raw).strip()
    # Strip :port suffix for IPv4
    if s.count(":") == 1 and "." in s:
        s = s.split(":", 1)[0]
    try:
        ip_obj = ipaddress.ip_address(s)
        return str(ip_obj), bool(ip_obj.is_private), ip_obj.version
    except ValueError:
        return None, None, None


def clean_text_for_match(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return re.sub(r"\s+", " ", str(raw)).strip().upper()
