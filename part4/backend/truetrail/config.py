
from pathlib import Path

# Project paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
OUT_DIR = ROOT_DIR / "out"
DOCS_DIR = ROOT_DIR / "docs"

# Input files
CDR_FILE = DATA_DIR / "cdr.csv"
IPDR_FILE = DATA_DIR / "ipdr.csv"
TXN_FILE = DATA_DIR / "txn.csv"
PINGS_FILE = DATA_DIR / "pings.csv"
TOWERS_FILE = DATA_DIR / "towers.csv"

# Output
TIMELINE_FILE = OUT_DIR / "timeline.json"

# Time settings
SOURCE_TIMEZONE = "Asia/Kolkata"
SESSION_GAP_MINUTES = 10

# Session thresholds
LONG_SESSION_HOURS = 2
SIGNATURE_SESSION_HOURS = 8

# Correlation windows
CORRELATION_WINDOWS = [5, 15, 60]
MIN_CONFIDENCE = 0.50

# Correlation feature weights
FEATURE_WEIGHTS = {
    "temporal_overlap": 0.25,
    "session_duration": 0.15,
    "new_payee": 0.15,
    "amount_anomaly": 0.15,
    "repeat_transfer": 0.10,
    "night_activity": 0.10,
    "round_amount": 0.10,
}

# Geolocation settings
GEOIP_DB = DATA_DIR / "GeoLite2-City.mmdb"
TOWER_RADIUS_METERS = 1000
IMPOSSIBLE_SPEED_KMPH = 120

# API settings
API_TITLE = "TrueTrail Timeline API"
API_VERSION = "1.0.0"

# Important limitations
ASSUMPTIONS = [
    "All source timestamps are assumed to be in Asia/Kolkata.",
    "Communication and transaction correlation does not prove causation.",
    "Cell tower coordinates represent approximate coverage areas.",
    "IP geolocation is approximate and may be inaccurate.",
    "Confidence scores are analytical indicators, not legal conclusions."
]
