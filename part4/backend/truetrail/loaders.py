
import hashlib
import pandas as pd

from . import config
from .timeutil import to_utc


def file_hash(path):
    """Generate SHA256 hash for source file."""
    if not path.exists():
        return None

    sha = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha.update(chunk)

    return sha.hexdigest()


def read_csv(path):
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def normalize_phone(value):
    if pd.isna(value):
        return None

    return str(value).strip()


def load_towers():
    df = read_csv(config.TOWERS_FILE)

    if df.empty:
        return df

    required = ["tower_id", "latitude", "longitude"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"towers.csv missing column: {col}")

    return df


def load_events():
    """Load CDR, IPDR and tower ping records into one event table."""

    records = []

    sources = [
        ("cdr", config.CDR_FILE, "timestamp"),
        ("ipdr", config.IPDR_FILE, "start_time"),
        ("ping", config.PINGS_FILE, "timestamp"),
    ]

    for source_name, path, time_column in sources:
        df = read_csv(path)

        if df.empty:
            continue

        if time_column not in df.columns:
            raise ValueError(
                f"{path.name} must contain '{time_column}' column"
            )

        for index, row in df.iterrows():
            timestamp = to_utc(row[time_column])

            if pd.isna(timestamp):
                continue

            victim = row.get("victim_id", row.get("phone_number"))

            records.append({
                "event_id": f"{source_name}_{index}",
                "event_type": source_name,
                "victim_id": normalize_phone(victim),
                "timestamp_utc": timestamp,
                "end_utc": to_utc(
                    row.get("end_time", row[time_column])
                ),
                "counterparty": row.get(
                    "counterparty",
                    row.get("destination_ip")
                ),
                "tower_id": row.get("tower_id"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "source_file": path.name,
                "source_row": int(index),
                "source_hash": file_hash(path),
            })

    events = pd.DataFrame(records)

    if events.empty:
        return events

    return events.sort_values("timestamp_utc").reset_index(drop=True)


def load_transactions():
    """Load and normalize UPI/NEFT transaction records."""

    df = read_csv(config.TXN_FILE)

    if df.empty:
        return df

    required = ["timestamp", "victim_id", "amount"]
    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"txn.csv missing required column: {col}"
            )

    df["timestamp_utc"] = df["timestamp"].apply(to_utc)
    df["victim_id"] = df["victim_id"].apply(normalize_phone)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    if "payee_id" not in df.columns:
        df["payee_id"] = None

    if "transaction_id" not in df.columns:
        df["transaction_id"] = [
            f"txn_{i}" for i in range(len(df))
        ]

    if "is_coerced" in df.columns:
        df["is_coerced"] = df["is_coerced"].map(
            lambda x: (
                str(x).strip().lower() in ["1", "true", "yes"]
                if pd.notna(x) else None
            )
        )

    return df.dropna(
        subset=["timestamp_utc", "victim_id", "amount"]
    ).sort_values("timestamp_utc").reset_index(drop=True)


def load_all():
    return {
        "events": load_events(),
        "transactions": load_transactions(),
        "towers": load_towers(),
    }
