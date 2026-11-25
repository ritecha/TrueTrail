"""
schemas.py  -  Canonical data contract (v1.1)   [shared by all 4 members]

Changes vs v1.0 (needed to match the real-format synthetic data):
  Transaction  : + rrn, direction, names, mobile, app_name, response_code, remarks, narration,
                 balance_after, source_type, corroborated_by      (bank statements carry narration/balance;
                 UPI logs carry names/app/response code; RRN is the key that links the two)
  CallRecord   : caller now Optional (hidden caller ID), + direction (IN/OUT from MOC/MTC),
                 target_number, raw_type, last_cell_id, lac, tower_address
  IPSession    : + private_ip, dst_port, protocol, imei, imsi, apn, cell_id, chunks
                 (src_ip == the PUBLIC IP, the one that matters for correlation)
  DeviceArtifact: + SMS type, direction, deleted flag, extra{} (package, version, last_used...)
  EvidenceItem : + rows_in / rejected_count / duplicate_count / schema_version
  NEW          : RejectedRow
Every datetime is validated to be timezone-aware and is converted to UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.1"


def _to_utc(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("naive datetime not allowed - normalise to UTC first")
    return v.astimezone(timezone.utc)


UTCDatetime = Annotated[datetime, AfterValidator(_to_utc)]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Transaction(_Base):
    txn_id: str
    rrn: Optional[str] = None                       # 12-digit UPI reference; links UPI log <-> statement
    timestamp: UTCDatetime
    channel: Literal["UPI", "IMPS", "NEFT", "RTGS", "ATM", "OTHER"]
    amount: float = Field(gt=0)
    currency: str = "INR"
    direction: Optional[Literal["DEBIT", "CREDIT"]] = None   # only known for bank statements
    sender_account: Optional[str] = None
    sender_vpa: Optional[str] = None
    sender_ifsc: Optional[str] = None
    sender_name: Optional[str] = None
    sender_mobile: Optional[str] = None
    receiver_account: Optional[str] = None
    receiver_vpa: Optional[str] = None
    receiver_ifsc: Optional[str] = None
    receiver_name: Optional[str] = None
    device_id: Optional[str] = None                 # payer app/device fingerprint (UPI log)
    ip_address: Optional[str] = None                # payer IP (UPI log)
    app_name: Optional[str] = None
    status: str = "SUCCESS"
    response_code: Optional[str] = None
    remarks: Optional[str] = None
    narration: Optional[str] = None                 # raw bank narration
    balance_after: Optional[float] = None
    source_type: Literal["UPI_LOG", "BANK_STATEMENT"]
    corroborated_by: list[str] = Field(default_factory=list)  # other files confirming this txn
    source_file: str                                # provenance
    source_row: int                                 # provenance


class CallRecord(_Base):
    record_id: str
    start_time: UTCDatetime
    end_time: Optional[UTCDatetime] = None
    duration_sec: int = Field(ge=0)
    caller: Optional[str] = None                    # E.164, None = hidden caller ID
    callee: str                                     # E.164
    target_number: Optional[str] = None             # the subscriber whose CDR this row is
    direction: Literal["IN", "OUT"]                 # MOC/SMS-MO -> OUT ; MTC/SMS-MT -> IN
    call_type: Literal["VOICE", "VIDEO", "SMS", "DATA"]
    raw_type: Optional[str] = None                  # MOC / MTC / SMS-MO / SMS-MT
    imei: Optional[str] = None
    imsi: Optional[str] = None
    cell_tower_id: Optional[str] = None             # first cell
    last_cell_id: Optional[str] = None
    lac: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    tower_address: Optional[str] = None
    source_file: str
    source_row: int


class IPSession(_Base):
    record_id: str
    start_time: UTCDatetime
    end_time: Optional[UTCDatetime] = None
    msisdn: Optional[str] = None                    # E.164
    imei: Optional[str] = None
    imsi: Optional[str] = None
    private_ip: Optional[str] = None
    src_ip: str                                     # PUBLIC IP of the subscriber
    src_port: Optional[int] = None
    dst_ip: Optional[str] = None
    dst_port: Optional[int] = None
    protocol: Optional[str] = None
    bytes_up: Optional[int] = None
    bytes_down: Optional[int] = None
    apn: Optional[str] = None
    cell_id: Optional[str] = None
    app_hint: Optional[str] = None                  # inferred from dst ip/port (config.APP_SIGNATURES)
    chunks: int = 1                                 # >1 when split IPDR records were merged
    source_file: str
    source_row: int


class DeviceArtifact(_Base):
    artifact_id: str
    device_id: str                                  # IMEI from the extraction report
    artifact_type: Literal["CHAT", "SMS", "INSTALLED_APP", "CONTACT", "CALL_LOG", "OTHER"]
    app: Optional[str] = None
    timestamp: Optional[UTCDatetime] = None
    direction: Optional[Literal["IN", "OUT"]] = None
    counterparty: Optional[str] = None
    content: Optional[str] = None
    deleted: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class EvidenceItem(_Base):
    evidence_id: str
    filename: str
    sha256: str
    evidence_type: str                              # upi | cdr | bank_statement | ipdr | device
    ingested_at: UTCDatetime
    record_count: int
    rows_in: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    schema_version: str = SCHEMA_VERSION


class RejectedRow(_Base):
    source_file: str
    source_row: int                                 # 0 = whole file / sheet rejected
    reason: str
    raw: Any = None


# ===========================================================================
# Additive Extended Schemas (v1.2) - Preserves all v1.1 entities untouched
# ===========================================================================

EXTENDED_SCHEMA_VERSION = "1.2"


class FieldProvenance(_Base):
    """Raw + normalized + confidence + exact source coordinates for any extracted field."""
    field_name: str
    raw_value: Optional[str] = None
    normalized_value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source_file: str
    source_page: Optional[int] = None
    source_row: int = 0
    source_column: Optional[str] = None
    original_timezone: Optional[str] = None


class CardTransaction(_Base):
    """4. Debit / Credit card transaction records."""
    record_id: str
    masked_card_number: str
    txn_id: Optional[str] = None
    merchant_id: Optional[str] = None
    terminal_id: Optional[str] = None
    acquiring_bank: Optional[str] = None
    amount: float = Field(gt=0)
    currency: str = "INR"
    timestamp: UTCDatetime
    auth_code: Optional[str] = None
    status: str = "SUCCESS"
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class BankingAccessLog(_Base):
    """5 & 6. Internet banking and Mobile banking access/session logs."""
    log_id: str
    channel: Literal["INTERNET_BANKING", "MOBILE_BANKING"]
    customer_id: Optional[str] = None
    account_id: Optional[str] = None
    registered_mobile: Optional[str] = None
    login_timestamp: UTCDatetime
    source_ip: Optional[str] = None
    session_id: Optional[str] = None
    device_id: Optional[str] = None
    device_browser_info: Optional[str] = None
    app_version: Optional[str] = None
    auth_event: Optional[str] = None
    txn_id: Optional[str] = None
    txn_details: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class WalletTransaction(_Base):
    """7. Payment wallet / PPI records."""
    record_id: str
    wallet_id: Optional[str] = None
    kyc_details: Optional[str] = None
    mobile_number: Optional[str] = None
    txn_ref: Optional[str] = None
    sender: Optional[str] = None
    receiver: Optional[str] = None
    amount: float = Field(gt=0)
    currency: str = "INR"
    timestamp: UTCDatetime
    linked_bank_account: Optional[str] = None
    status: str = "SUCCESS"
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class BankKYCRecord(_Base):
    """8. Bank KYC and account-opening records."""
    record_id: str
    account_number: Optional[str] = None
    ifsc: Optional[str] = None
    account_holder_name: Optional[str] = None
    address: Optional[str] = None
    dob: Optional[str] = None
    pan: Optional[str] = None
    masked_aadhaar: Optional[str] = None
    registered_mobile: Optional[str] = None
    email: Optional[str] = None
    account_opening_date: Optional[UTCDatetime] = None
    kyc_verification_details: Optional[str] = None
    ocr_confidence: Optional[float] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class CellTowerRecord(_Base):
    """11. Cell tower / location records."""
    record_id: str
    cell_id: str
    lac: Optional[str] = None
    sector_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    tower_address: Optional[str] = None
    timestamp: UTCDatetime
    msisdn: Optional[str] = None
    imei: Optional[str] = None
    imsi: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class SIMChangeRecord(_Base):
    """12. SIM change / SIM swap records."""
    record_id: str
    msisdn: str
    old_imsi: Optional[str] = None
    new_imsi: Optional[str] = None
    activation_time: Optional[UTCDatetime] = None
    replacement_request_time: Optional[UTCDatetime] = None
    subscriber_details: Optional[str] = None
    request_channel: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class SMSRecord(_Base):
    """13. Operator SMS records."""
    record_id: str
    message_id: Optional[str] = None
    sender_number: Optional[str] = None
    receiver_number: Optional[str] = None
    timestamp: UTCDatetime
    delivery_status: Optional[str] = None
    sms_category: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class ISPSubscriberRecord(_Base):
    """14. ISP subscriber records."""
    record_id: str
    customer_id: Optional[str] = None
    subscriber_name: Optional[str] = None
    registered_address: Optional[str] = None
    ip_allocation_details: Optional[str] = None
    assigned_ip: Optional[str] = None
    connection_start: Optional[UTCDatetime] = None
    connection_end: Optional[UTCDatetime] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class IPAllocationLog(_Base):
    """15. IP allocation / session logs."""
    record_id: str
    subscriber_id: Optional[str] = None
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    port_number: Optional[int] = None
    session_start: UTCDatetime
    session_end: Optional[UTCDatetime] = None
    original_timestamp: Optional[str] = None
    original_timezone: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class DNSRecord(_Base):
    """16. DNS query & resolution logs."""
    record_id: str
    domain: str
    queried_hostname: Optional[str] = None
    resolved_ip: Optional[str] = None
    query_timestamp: UTCDatetime
    record_type: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class VPNProxyRecord(_Base):
    """17. VPN / proxy service records."""
    record_id: str
    account_id: Optional[str] = None
    assigned_ip: Optional[str] = None
    source_ip: Optional[str] = None
    connection_timestamp: UTCDatetime
    session_duration_sec: Optional[int] = Field(default=None, ge=0)
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class CyberComplaintRecord(_Base):
    """18. National Cyber Crime Reporting Portal (NCRP) complaints."""
    record_id: str
    acknowledgement_no: Optional[str] = None
    incident_timestamp: Optional[UTCDatetime] = None
    complaint_description: Optional[str] = None
    victim_details: Optional[str] = None
    bank_or_wallet: Optional[str] = None
    utr: Optional[str] = None
    amount: Optional[float] = None
    suspect_identifiers: list[str] = Field(default_factory=list)
    ocr_confidence: Optional[float] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class FIRRecord(_Base):
    """19. FIR and police complaints."""
    record_id: str
    fir_number: Optional[str] = None
    police_station: Optional[str] = None
    sections_invoked: list[str] = Field(default_factory=list)
    complainant_details: Optional[str] = None
    incident_chronology: Optional[str] = None
    accused_details: Optional[str] = None
    fir_timestamp: Optional[UTCDatetime] = None
    ocr_confidence: Optional[float] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


class PaymentArtifactRecord(_Base):
    """20 & 21. Victim-provided transaction screenshots & payment receipts."""
    record_id: str
    artifact_kind: Literal["TXN_SCREENSHOT", "PAYMENT_RECEIPT"]
    txn_id: Optional[str] = None
    txn_ref: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "INR"
    timestamp: Optional[UTCDatetime] = None
    sender_details: Optional[str] = None
    receiver_details: Optional[str] = None
    bank_or_wallet: Optional[str] = None
    merchant_id: Optional[str] = None
    ocr_confidence: Optional[float] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    source_row: int


# ---------------------------------------------------------------------------
# Canonical Correlation Layer (Events, Entities, Links)
# ---------------------------------------------------------------------------

class NormalizedEvent(_Base):
    event_id: str
    event_type: str
    timestamp: Optional[UTCDatetime] = None
    amount: Optional[float] = None
    duration_sec: Optional[int] = None
    status: Optional[str] = None
    source_schema: str
    source_record_id: str
    evidence_id: str
    source_file: str
    source_row: int
    attributes: dict[str, Any] = Field(default_factory=dict)


class CanonicalEntity(_Base):
    entity_id: str
    entity_type: Literal[
        "PHONE", "ACCOUNT", "VPA", "IFSC", "IP", "IMEI", "IMSI",
        "DEVICE_ID", "CARD", "PAN", "PERSON", "DOMAIN", "UTR", "EMAIL", "CELL_ID", "OTHER"
    ]
    normalized_value: str
    raw_examples: list[str] = Field(default_factory=list)
    is_private_ip: Optional[bool] = None
    ip_version: Optional[int] = None


class EntityEventLink(_Base):
    link_id: str
    entity_id: str
    event_id: str
    role: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source_file: str
    source_row: int


# ---------------------------------------------------------------------------
# Pipeline Governance: Validation Flags, Review Queue, Custody, AI Logs, Jobs
# ---------------------------------------------------------------------------

class ValidationFlag(_Base):
    flag_id: str
    evidence_id: str
    source_file: str
    source_row: int
    field_name: str
    severity: Literal["INFO", "WARNING", "ERROR"]
    rule_name: str
    message: str
    raw_value: Optional[str] = None


class ReviewItem(_Base):
    review_id: str
    evidence_id: str
    source_file: str
    column_name: Optional[str] = None
    source_row: int = 0
    review_type: Literal[
        "COLUMN_MAPPING", "AMBIGUOUS_ENTITY", "LOW_CONFIDENCE_OCR", "VALIDATION_FAILURE"
    ]
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    sample_values: list[str] = Field(default_factory=list)
    recommended: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    resolved_value: Optional[str] = None
    reviewer: Optional[str] = None
    resolved_at: Optional[UTCDatetime] = None


class CustodyLogEntry(_Base):
    log_id: str
    evidence_id: str
    action: str
    actor: str
    actor_ip: Optional[str] = None
    sha256_at_event: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: UTCDatetime


class AIInterpretationLog(_Base):
    log_id: str
    evidence_id: str
    task: str
    model_name: str
    model_version: str
    temperature: float = 0.0
    prompt_hash: str
    input_summary: str
    output_json: dict[str, Any] = Field(default_factory=dict)
    deterministic_verified: bool = True
    verification_notes: Optional[str] = None
    created_at: UTCDatetime


class IngestJob(_Base):
    job_id: str
    evidence_id: str
    filename: str
    sha256: str
    status: Literal["QUEUED", "PROCESSING", "NEEDS_REVIEW", "COMPLETED", "FAILED"]
    progress_pct: int = Field(ge=0, le=100, default=0)
    stage: str = "INTAKE"
    error: Optional[str] = None
    created_at: UTCDatetime
    updated_at: UTCDatetime
