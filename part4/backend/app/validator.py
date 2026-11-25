"""
validator.py - Stage 7: Deterministic forensic sanity checks.
Failures are flagged in validation_flags and NEVER silently fixed or overwritten.
"""
from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
from app.disambiguator import luhn_valid
from schemas import Transaction, ValidationFlag


def make_flag(
    evidence_id: str,
    source_file: str,
    source_row: int,
    field_name: str,
    severity: str,
    rule_name: str,
    message: str,
    raw_value: Optional[str] = None,
) -> ValidationFlag:
    return ValidationFlag(
        flag_id=f"flg_{uuid.uuid4().hex[:12]}",
        evidence_id=evidence_id,
        source_file=source_file,
        source_row=source_row,
        field_name=field_name,
        severity=severity,
        rule_name=rule_name,
        message=message,
        raw_value=raw_value,
    )


def validate_date_plausibility(
    dt: Optional[datetime],
    evidence_id: str,
    source_file: str,
    source_row: int,
    field_name: str,
) -> list[ValidationFlag]:
    if dt is None:
        return []
    flags: list[ValidationFlag] = []
    min_dt = datetime(1995, 1, 1, tzinfo=timezone.utc)
    max_dt = datetime.now(timezone.utc) + timedelta(days=1)
    if dt < min_dt or dt > max_dt:
        flags.append(
            make_flag(
                evidence_id,
                source_file,
                source_row,
                field_name,
                "WARNING",
                "DATE_PLAUSIBILITY",
                f"Timestamp {dt.isoformat()} outside plausible forensic bounds",
                dt.isoformat(),
            )
        )
    return flags


def validate_ifsc(
    ifsc: Optional[str],
    evidence_id: str,
    source_file: str,
    source_row: int,
    field_name: str,
) -> list[ValidationFlag]:
    if not ifsc:
        return []
    if not re.match(config.REGEX_PATTERNS["ifsc"], ifsc.strip().upper()):
        return [
            make_flag(
                evidence_id,
                source_file,
                source_row,
                field_name,
                "WARNING",
                "IFSC_FORMAT",
                f"Invalid IFSC structure: '{ifsc}'",
                ifsc,
            )
        ]
    return []


def validate_imei(
    imei: Optional[str],
    evidence_id: str,
    source_file: str,
    source_row: int,
    field_name: str = "imei",
) -> list[ValidationFlag]:
    if not imei:
        return []
    digits = imei.strip()
    if not (len(digits) == 15 and luhn_valid(digits)):
        return [
            make_flag(
                evidence_id,
                source_file,
                source_row,
                field_name,
                "WARNING",
                "IMEI_LUHN",
                f"IMEI '{imei}' failed 15-digit Luhn checksum",
                imei,
            )
        ]
    return []


def validate_ip(
    ip_str: Optional[str],
    evidence_id: str,
    source_file: str,
    source_row: int,
    field_name: str = "ip_address",
) -> list[ValidationFlag]:
    if not ip_str:
        return []
    try:
        ipaddress.ip_address(ip_str.strip())
        return []
    except ValueError:
        return [
            make_flag(
                evidence_id,
                source_file,
                source_row,
                field_name,
                "WARNING",
                "IP_FORMAT",
                f"Invalid IP address '{ip_str}'",
                ip_str,
            )
        ]


def validate_bank_running_balance(
    txns: list[Transaction],
    evidence_id: str,
) -> list[ValidationFlag]:
    """
    Verifies running balance consistency across bank statement rows.
    Flags anomalies without modifying amounts or balances.
    """
    flags: list[ValidationFlag] = []
    prev_bal: Optional[float] = None
    for txn in txns:
        if txn.balance_after is None:
            continue
        if prev_bal is not None and txn.direction in {"DEBIT", "CREDIT"}:
            expected = prev_bal - txn.amount if txn.direction == "DEBIT" else prev_bal + txn.amount
            if abs(expected - txn.balance_after) > 0.05:
                flags.append(
                    make_flag(
                        evidence_id=evidence_id,
                        source_file=txn.source_file,
                        source_row=txn.source_row,
                        field_name="balance_after",
                        severity="ERROR",
                        rule_name="RUNNING_BALANCE_MISMATCH",
                        message=(
                            f"Running balance mismatch: prev={prev_bal:.2f}, "
                            f"{txn.direction}={txn.amount:.2f}, expected={expected:.2f}, "
                            f"actual={txn.balance_after:.2f}"
                        ),
                        raw_value=str(txn.balance_after),
                    )
                )
        prev_bal = txn.balance_after
    return flags
