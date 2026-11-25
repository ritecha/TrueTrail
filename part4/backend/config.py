from datetime import timedelta, timezone
import os
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

# files that are never evidence
IGNORE_FILES = {"ground_truth.json", "SHA256SUMS.txt"}

# --------------------------------------------------------------------------- UPI switch / PSP log
UPI = {
    "assume_tz": UTC,
    "date_formats": [],                                   # ISO-8601 handled natively
    "required": ["txn_id", "timestamp", "amount"],
    "columns": {
        "txn_id": ["Txn_ID", "Transaction ID", "TxnId"],
        "rrn": ["RRN", "Ref No", "UPI Ref No"],
        "timestamp": ["Txn_Timestamp_UTC", "Txn Timestamp", "Transaction Date Time", "Timestamp"],
        "txn_type": ["Txn_Type", "Type"],
        "payer_vpa": ["Payer_VPA", "Payer VPA", "Remitter VPA"],
        "payer_name": ["Payer_Name", "Remitter Name"],
        "payer_account": ["Payer_Account", "Payer Acct", "Remitter Account"],
        "payer_ifsc": ["Payer_IFSC", "Remitter IFSC"],
        "payer_mobile": ["Payer_Mobile", "Payer Mobile No"],
        "payee_vpa": ["Payee_VPA", "Payee VPA", "Beneficiary VPA"],
        "payee_name": ["Payee_Name", "Beneficiary Name"],
        "payee_account": ["Payee_Account", "Beneficiary Account"],
        "payee_ifsc": ["Payee_IFSC", "Beneficiary IFSC"],
        "amount": ["Amount", "Txn Amount", "Amount (INR)"],
        "currency": ["Currency"],
        "status": ["Status", "Txn Status"],
        "response_code": ["Response_Code", "Resp Code"],
        "device_id": ["Device_ID", "Device Id", "Payer Device"],
        "ip": ["Device_IP", "IP Address", "Payer IP"],
        "app_name": ["App_Name", "PSP App"],
        "remarks": ["Remarks", "Note"],
    },
}

# --------------------------------------------------------------------------- Telecom CDR
CDR = {
    "assume_tz": UTC,                                     # epoch seconds are UTC by definition
    "required": ["called", "call_type", "start"],
    "columns": {
        "calling": ["CALLING_NO", "A_PARTY", "Calling Number", "A Party"],
        "called": ["CALLED_NO", "B_PARTY", "Called Number", "B Party"],
        "call_type": ["CALL_TYPE", "Call Type"],
        "service": ["SERVICE", "Service Type"],
        "start": ["START_EPOCH", "Call Start", "Start Time"],
        "duration": ["DURATION_SEC", "Duration"],
        "imei": ["IMEI"],
        "imsi": ["IMSI"],
        "first_cell": ["FIRST_CELL_ID", "Cell ID A", "Cell ID"],
        "last_cell": ["LAST_CELL_ID", "Last Cell ID"],
        "lac": ["LAC"],
        "lat": ["TOWER_LAT", "Latitude"],
        "lon": ["TOWER_LON", "Longitude"],
        "address": ["TOWER_ADDR", "Site Address", "Address"],
    },
}
CDR_DIRECTION = {"MOC": "OUT", "SMS-MO": "OUT", "MTC": "IN", "SMS-MT": "IN"}
CDR_SERVICE = {"VOICE": "VOICE", "VIDEO": "VIDEO", "SMS": "SMS", "DATA": "DATA"}
CDR_TARGET_IS_CALLER = {"OUT": True, "IN": False}

# --------------------------------------------------------------------------- Telecom IPDR
IPDR = {
    "assume_tz": IST,
    "date_formats": ["%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"],
    "required": ["msisdn", "public_ip", "start"],
    "columns": {
        "msisdn": ["MSISDN", "Subscriber Number"],
        "imei": ["IMEI"],
        "imsi": ["IMSI"],
        "private_ip": ["PRIVATE_IP", "Private IP"],
        "public_ip": ["PUBLIC_IP", "Public IP", "Source Public IP"],
        "src_port": ["SRC_PORT", "Source Port"],
        "dst_ip": ["DST_IP", "Destination IP"],
        "dst_port": ["DST_PORT", "Destination Port"],
        "protocol": ["PROTOCOL"],
        "start": ["START_TIME", "Session Start"],
        "end": ["END_TIME", "Session End"],
        "up": ["UPLINK_BYTES", "Uplink Volume"],
        "down": ["DOWNLINK_BYTES", "Downlink Volume"],
        "apn": ["APN"],
        "cell_id": ["CELL_ID", "Cell Id"],
    },
}
# (dst_ip, dst_port) -> label.  Real life: build from IP-range lookups / lawful-intercept notes.
APP_SIGNATURES = {
    ("203.0.113.45", 3478): "WhatsApp (call relay)",
    ("198.51.100.77", 7070): "AnyDesk (remote access)",
    ("192.0.2.10", 443): "Mobile banking app",
}
IPDR_MERGE_GAP_SEC = 5          # contiguous chunks (gap <= this) of the same flow become one session

# --------------------------------------------------------------------------- Bank statements (xlsx)
BANK_PROFILES = {
    "default": {
        "assume_tz": IST,
        "date_formats": ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"],
        "required": ["txn_date", "narration"],
        "columns": {
            "txn_date": ["Txn Date", "Transaction Date", "Date"],
            "value_date": ["Value Date"],
            "narration": ["Narration", "Description", "Particulars", "Transaction Remarks"],
            "ref_no": ["Chq/Ref No", "Ref No", "Cheque No", "Reference"],
            "debit": ["Withdrawal Amt (Dr)", "Withdrawal", "Debit", "Dr Amount"],
            "credit": ["Deposit Amt (Cr)", "Deposit", "Credit", "Cr Amount"],
            "balance": ["Closing Balance", "Balance"],
        },
        # metadata block above the table:  canonical -> label aliases
        "meta_labels": {
            "account_no": ["Account No", "Account Number", "A/c No"],
            "account_name": ["Account Name", "Customer Name"],
            "ifsc": ["IFSC", "IFSC Code"],
        },
        "title_prefix": "STATEMENT OF ACCOUNT",
        # ordered (regex, channel) - first match wins; UPI is parsed with UPI_NARRATION below
        "channel_rules": [
            (r"^UPI", "UPI"), (r"^NEFT", "NEFT"), (r"^IMPS", "IMPS"),
            (r"^RTGS", "RTGS"), (r"^ATM", "ATM"),
        ],
        "upi_narration": r"^UPI-(?P<name>.+?)-(?P<vpa>[\w.\-]+@[A-Za-z0-9]+)-(?P<ifsc>[A-Z]{4}0[A-Z0-9]{6})-(?P<rrn>\d{12})-?(?P<remark>.*)$",
    },
    # add "sbi": {...}, "icici": {...} here when a new statement layout shows up
}

# --------------------------------------------------------------------------- Device forensics (Cellebrite-style JSON)
DEVICE = {
    "assume_tz": IST,                                     # suffix "(UTC+5:30)" is parsed and wins
    "date_formats": ["%d-%m-%Y %H:%M:%S"],
}


# ===========================================================================
# Extended Runtime & Forensic Pipeline Configuration
# ===========================================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("FORENSIC_DATA_DIR", str(BASE_DIR / "data")))
VAULT_DIR = DATA_DIR / "vault"
WORKSPACE_DIR = DATA_DIR / "workspace"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'forensics.db'}")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if o.strip()
]

# AI service defaults: local-first, deterministic, optional cloud only if explicitly enabled
AI_PROVIDER = os.environ.get("AI_PROVIDER", "none").lower()  # none | ollama | gemini
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ALLOW_CLOUD_AI = os.environ.get("ALLOW_CLOUD_AI", "false").lower() == "true"

# Confidence thresholds for 6-rung header mapper & OCR
MAPPING_ACCEPT_THRESHOLD = 0.78
MAPPING_REVIEW_THRESHOLD = 0.45
OCR_REVIEW_THRESHOLD = 0.65
DISAMBIGUATION_MARGIN = 0.15

# Extra Indian date formats supported across banks / telcos / portals
COMMON_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%b-%Y %H:%M:%S",
    "%d-%b-%Y",
    "%d %b %Y %H:%M:%S",
    "%d %b %Y",
]

# Regex patterns for deterministic validation & content-based detection (Rung 3 & Section 4)
REGEX_PATTERNS = {
    "ifsc": r"^[A-Z]{4}0[A-Z0-9]{6}$",
    "pan": r"^[A-Z]{5}[0-9]{4}[A-Z]$",
    "vpa": r"^[a-zA-Z0-9._\-]{2,}@[a-zA-Z0-9]{2,}$",
    "indian_mobile": r"^(?:\+91|91|0)?([6-9]\d{9})$",
    "imei": r"^\d{15}$",
    "imsi_india": r"^40[45]\d{12}$",
    "rrn": r"^\d{12}$",
    "masked_card": r"^(?:\d{4,6}[Xx*]{4,8}\d{4}|\*{4}\s?\*{4}\s?\*{4}\s?\d{4}|X{4,12}\d{4})$",
    "masked_aadhaar": r"^(?:[Xx*]{4}[\s\-]?[Xx*]{4}[\s\-]?\d{4}|\d{4}\s?\d{4}\s?\d{4})$",
    "ipv4": r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$",
    "email": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
    "domain": r"^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$",
    "amount_indian": r"^[₹RsINR\.\s\-+]*\d{1,3}(?:,\d{2,3})*(?:\.\d{1,4})?(?:\s*(?:Dr|Cr|DR|CR))?$",
}

# Extended evidence type definitions & column aliases for the 21 forensic sources
EXTENDED_EVIDENCE_PROFILES = {
    "interbank_transfer": {
        "assume_tz": IST,
        "required": ["amount", "timestamp"],
        "columns": {
            "rrn": ["UTR", "UTR No", "UTR/Reference", "Reference Number", "Ref No", "RRN"],
            "txn_id": ["Txn ID", "Transaction ID", "Tran ID"],
            "sender_account": ["Remitter Account", "Remitter A/c", "From Account", "Debit Account"],
            "receiver_account": ["Beneficiary Account", "Beneficiary A/c", "To Account", "Credit Account"],
            "sender_ifsc": ["Remitter IFSC", "Sender IFSC"],
            "receiver_ifsc": ["Beneficiary IFSC", "IFSC", "IFSC Code"],
            "sender_name": ["Remitter Name", "Sender Name"],
            "receiver_name": ["Beneficiary Name", "Receiver Name"],
            "amount": ["Amount", "Txn Amount", "Transfer Amount", "Amount (INR)"],
            "timestamp": ["Timestamp", "Txn Date", "Transaction Date", "Date Time", "Value Date"],
            "status": ["Status", "Transaction Status", "Txn Status"],
            "channel": ["Channel", "Mode", "Transfer Type", "Type"],
            "remarks": ["Remarks", "Narration", "Remitter Details", "Beneficiary Details"],
        },
    },
    "card_transaction": {
        "assume_tz": IST,
        "required": ["masked_card_number", "amount", "timestamp"],
        "columns": {
            "masked_card_number": ["Masked Card Number", "Card Number", "Card No", "Masked Card"],
            "txn_id": ["Transaction ID", "Txn ID", "Tran ID"],
            "merchant_id": ["Merchant ID", "MID", "Merchant"],
            "terminal_id": ["Terminal ID", "TID"],
            "acquiring_bank": ["Acquiring Bank", "Acquirer", "Bank Name"],
            "amount": ["Amount", "Txn Amount", "Billing Amount"],
            "currency": ["Currency"],
            "timestamp": ["Timestamp", "Txn Date", "Transaction Date", "Date Time"],
            "auth_code": ["Authorization Code", "Auth Code", "Approval Code"],
            "status": ["Status", "Transaction Status", "Response"],
        },
    },
    "internet_banking_log": {
        "assume_tz": IST,
        "required": ["login_timestamp"],
        "columns": {
            "customer_id": ["Customer ID", "Cust ID", "User ID", "Account ID"],
            "account_id": ["Account ID", "Account Number", "A/c No"],
            "login_timestamp": ["Login Timestamp", "Login Time", "Timestamp", "Event Time"],
            "source_ip": ["Source IP", "IP Address", "Client IP", "IP"],
            "session_id": ["Session ID", "Session"],
            "device_browser_info": ["Device/Browser", "User Agent", "Browser", "Device Info"],
            "auth_event": ["Authentication Event", "Auth Event", "Event", "Event Type", "Status"],
            "txn_id": ["Transaction ID", "Txn ID", "Reference ID"],
        },
    },
    "mobile_banking_log": {
        "assume_tz": IST,
        "required": ["login_timestamp"],
        "columns": {
            "customer_id": ["Customer ID", "Cust ID", "User ID"],
            "registered_mobile": ["Registered Mobile", "Mobile Number", "MSISDN", "Phone"],
            "device_id": ["Device ID", "Device Fingerprint", "IMEI", "UUID"],
            "app_version": ["App Version", "Version"],
            "login_timestamp": ["Login Time", "Login Timestamp", "Timestamp"],
            "source_ip": ["IP Address", "Source IP", "Client IP"],
            "session_id": ["Session ID", "Session"],
            "txn_details": ["Transaction Details", "Txn Details", "Remarks", "Action"],
            "txn_id": ["Transaction ID", "Txn ID"],
        },
    },
    "wallet_record": {
        "assume_tz": IST,
        "required": ["amount", "timestamp"],
        "columns": {
            "wallet_id": ["Wallet ID", "Account ID", "PPI ID"],
            "kyc_details": ["KYC Details", "KYC Level", "KYC Status"],
            "mobile_number": ["Mobile Number", "Phone", "Registered Mobile"],
            "txn_ref": ["Transaction Reference", "Txn Ref", "Txn ID", "UTR"],
            "sender": ["Sender", "From", "Payer"],
            "receiver": ["Receiver", "To", "Payee"],
            "amount": ["Amount", "Txn Amount"],
            "timestamp": ["Timestamp", "Date Time", "Txn Date"],
            "linked_bank_account": ["Linked Bank Account", "Bank Account", "Linked A/c"],
            "status": ["Status", "Txn Status"],
        },
    },
    "bank_kyc": {
        "assume_tz": IST,
        "required": [],
        "columns": {
            "account_number": ["Account Number", "Account No", "A/c No"],
            "ifsc": ["IFSC", "IFSC Code"],
            "account_holder_name": ["Account Holder Name", "Customer Name", "Name", "Applicant Name"],
            "address": ["Address", "Permanent Address", "Communication Address"],
            "dob": ["DOB", "Date of Birth"],
            "pan": ["PAN", "PAN Number", "PAN No"],
            "masked_aadhaar": ["Masked Aadhaar", "Aadhaar", "UID"],
            "registered_mobile": ["Registered Mobile", "Mobile Number", "Phone"],
            "email": ["Email", "Email ID"],
            "account_opening_date": ["Account Opening Date", "Opening Date", "Open Date"],
            "kyc_verification_details": ["KYC Verification", "KYC Status", "Verification Details"],
        },
    },
    "cell_tower": {
        "assume_tz": IST,
        "required": ["cell_id", "timestamp"],
        "columns": {
            "cell_id": ["Cell ID", "CGI", "Cell_ID"],
            "lac": ["LAC"],
            "sector_id": ["Sector ID", "Sector"],
            "latitude": ["Latitude", "Lat", "Tower Lat"],
            "longitude": ["Longitude", "Lon", "Lng", "Tower Lon"],
            "tower_address": ["Tower Address", "Site Address", "Address", "Location"],
            "timestamp": ["Timestamp", "Date Time", "Event Time"],
            "msisdn": ["Mobile Number", "MSISDN", "Phone"],
            "imei": ["IMEI"],
            "imsi": ["IMSI"],
        },
    },
    "sim_swap": {
        "assume_tz": IST,
        "required": ["msisdn"],
        "columns": {
            "msisdn": ["Mobile Number", "MSISDN", "Subscriber Number"],
            "old_imsi": ["Old IMSI", "Previous IMSI"],
            "new_imsi": ["New IMSI", "Current IMSI"],
            "activation_time": ["SIM Activation Time", "Activation Time", "Activated At"],
            "replacement_request_time": ["Replacement Request Time", "Request Time", "Requested At"],
            "subscriber_details": ["Subscriber Details", "Subscriber Name", "Customer Name"],
            "request_channel": ["Request Channel", "Channel", "Store/Portal"],
        },
    },
    "sms_record": {
        "assume_tz": IST,
        "required": ["timestamp"],
        "columns": {
            "sender_number": ["Sender Number", "Sender", "A_PARTY", "From"],
            "receiver_number": ["Receiver Number", "Receiver", "B_PARTY", "To"],
            "timestamp": ["Timestamp", "Date Time", "Sent Time"],
            "delivery_status": ["Message Delivery Status", "Delivery Status", "Status"],
            "message_id": ["Message ID", "Msg ID", "SMS ID"],
            "sms_category": ["SMS Category", "Category", "Type"],
        },
    },
    "isp_subscriber": {
        "assume_tz": IST,
        "required": [],
        "columns": {
            "customer_id": ["Customer ID", "Subscriber ID", "Account ID"],
            "subscriber_name": ["Subscriber Name", "Customer Name", "Name"],
            "registered_address": ["Registered Address", "Address", "Installation Address"],
            "ip_allocation_details": ["IP Allocation Details", "IP Details", "Pool"],
            "assigned_ip": ["Assigned IP", "Static IP", "IP Address", "Public IP"],
            "connection_start": ["Connection Start", "Start Date", "Activation Date"],
            "connection_end": ["Connection End", "End Date", "Deactivation Date"],
        },
    },
    "ip_allocation": {
        "assume_tz": UTC,
        "required": ["session_start"],
        "columns": {
            "public_ip": ["Public IP", "NAT IP", "Assigned Public IP"],
            "private_ip": ["Private IP", "Internal IP"],
            "port_number": ["Port Number", "Port", "Src Port", "Translated Port"],
            "subscriber_id": ["Subscriber ID", "Customer ID", "User ID", "MSISDN"],
            "session_start": ["Session Start", "Start Time", "Timestamp"],
            "session_end": ["Session End", "End Time"],
            "original_timezone": ["Timezone", "TZ"],
        },
    },
    "dns_record": {
        "assume_tz": UTC,
        "required": ["domain", "query_timestamp"],
        "columns": {
            "domain": ["Domain", "Base Domain"],
            "queried_hostname": ["Queried Hostname", "Hostname", "QNAME", "Query"],
            "resolved_ip": ["Resolved IP", "Answer IP", "IP", "A Record"],
            "query_timestamp": ["Query Timestamp", "Timestamp", "Time"],
            "record_type": ["Record Type", "QTYPE", "Type"],
        },
    },
    "vpn_proxy": {
        "assume_tz": UTC,
        "required": ["connection_timestamp"],
        "columns": {
            "account_id": ["Account ID", "User ID", "Username"],
            "assigned_ip": ["Assigned IP", "VPN IP", "Virtual IP"],
            "source_ip": ["Source IP", "Real IP", "Client IP"],
            "connection_timestamp": ["Connection Timestamp", "Connected At", "Timestamp"],
            "session_duration_sec": ["Session Duration", "Duration", "Duration Sec"],
        },
    },
}
