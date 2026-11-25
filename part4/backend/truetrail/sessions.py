
import pandas as pd

from .config import (
    SESSION_GAP_MINUTES,
    LONG_SESSION_HOURS,
    SIGNATURE_SESSION_HOURS,
)


def build_sessions(events):
    if events.empty:
        return pd.DataFrame()

    ipdr = events[
        events["event_type"] == "ipdr"
    ].copy()

    if ipdr.empty:
        return pd.DataFrame()

    ipdr = ipdr.dropna(
        subset=["victim_id", "timestamp_utc"]
    )

    ipdr["end_utc"] = ipdr["end_utc"].fillna(
        ipdr["timestamp_utc"]
    )

    ipdr = ipdr.sort_values(
        ["victim_id", "timestamp_utc"]
    )

    sessions = []

    for victim, group in ipdr.groupby("victim_id"):
        group = group.sort_values("timestamp_utc")

        current = None

        for _, row in group.iterrows():
            destination = row.get("counterparty")

            if current is None:
                current = {
                    "victim_id": victim,
                    "destination_ip": destination,
                    "start_utc": row["timestamp_utc"],
                    "end_utc": row["end_utc"],
                    "event_count": 1,
                    "event_ids": [row["event_id"]],
                }
                continue

            gap = (
                row["timestamp_utc"] - current["end_utc"]
            ).total_seconds() / 60

            same_destination = (
                destination == current["destination_ip"]
            )

            if gap <= SESSION_GAP_MINUTES and same_destination:
                current["end_utc"] = max(
                    current["end_utc"], row["end_utc"]
                )
                current["event_count"] += 1
                current["event_ids"].append(row["event_id"])
            else:
                sessions.append(current)

                current = {
                    "victim_id": victim,
                    "destination_ip": destination,
                    "start_utc": row["timestamp_utc"],
                    "end_utc": row["end_utc"],
                    "event_count": 1,
                    "event_ids": [row["event_id"]],
                }

        if current is not None:
            sessions.append(current)

    result = pd.DataFrame(sessions)

    if result.empty:
        return result

    result["duration_hours"] = (
        result["end_utc"] - result["start_utc"]
    ).dt.total_seconds() / 3600

    result["is_long_session"] = (
        result["duration_hours"] >= LONG_SESSION_HOURS
    )

    result["is_signature_session"] = (
        result["duration_hours"] >= SIGNATURE_SESSION_HOURS
    )

    result["session_type"] = "NORMAL"

    result.loc[
        result["is_long_session"], "session_type"
    ] = "LONG_SESSION"

    result.loc[
        result["is_signature_session"], "session_type"
    ] = "DIGITAL_ARREST_SIGNATURE"

    result["session_id"] = [
        f"session_{i}" for i in range(len(result))
    ]

    return result
