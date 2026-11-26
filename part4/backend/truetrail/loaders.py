import hashlib
import pandas as pd
import re
from . import config
from .timeutil import to_utc

def file_hash(path):
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
    df = pd.read_csv(path)
    
    # Auto-detect and rename columns
    aliases = {
        "timestamp": ["timestamp", "date", "time", "datetime", "call_time", "start_time", "start", "txn_date"],
        "victim_id": ["victim_id", "victim", "phone_number", "calling", "caller", "msisdn", "sender", "account_number"],
        "amount": ["amount", "amt", "value", "transaction_amount", "txn_amount"],
        "counterparty": ["counterparty", "called", "receiver", "payee", "destination"],
        "tower_id": ["tower_id", "cell_id", "first_cell"],
        "latitude": ["latitude", "lat", "tower_lat"],
        "longitude": ["longitude", "lon", "lng", "tower_lon"],
    }
    
    rename_dict = {}
    for col in df.columns:
        c = str(col).strip().lower().replace(" ", "_")
        for target, vars in aliases.items():
            if c in vars:
                rename_dict[col] = target
                break
                
    df = df.rename(columns=rename_dict)
    
    # Fallback: Agar timestamp nahi hai, toh pehle column ko hi timestamp maan lo
    if "timestamp" not in df.columns and len(df.columns) > 0:
        df = df.rename(columns={df.columns[0]: "timestamp"})
        
    return df

def load_towers():
    df = read_csv(config.TOWERS_FILE)
    return df

def load_events():
    records = []
    sources = [("cdr", config.CDR_FILE), ("ipdr", config.IPDR_FILE), ("ping", config.PINGS_FILE)]
    
    for source_name, path in sources:
        df = read_csv(path)
        if df.empty: continue
        
        for index, row in df.iterrows():
            if "timestamp" not in row or pd.isna(row["timestamp"]):
                continue
                
            timestamp = to_utc(row["timestamp"])
            victim = row.get("victim_id", "Unknown")
            
            records.append({
                "event_id": f"{source_name}_{index}",
                "event_type": source_name,
                "victim_id": str(victim),
                "timestamp_utc": timestamp,
                "end_utc": timestamp, # Simplification for prototype
                "counterparty": str(row.get("counterparty", "Unknown")),
                "tower_id": str(row.get("tower_id", "Unknown")),
                "latitude": row.get("latitude", 28.6139),
                "longitude": row.get("longitude", 77.2090),
                "source_file": path.name,
            })
            
    events = pd.DataFrame(records)
    return events

def load_transactions():
    df = read_csv(config.TXN_FILE)
    if not df.empty and "timestamp" in df.columns:
        df["timestamp_utc"] = df["timestamp"].apply(to_utc)
    return df

def load_all():
    return {
        "events": load_events(),
        "transactions": load_transactions(),
        "towers": load_towers(),
    }