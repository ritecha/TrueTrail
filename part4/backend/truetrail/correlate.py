
import pandas as pd

from .config import (
    CORRELATION_WINDOWS,
    FEATURE_WEIGHTS,
    MIN_CONFIDENCE,
)


def score_transaction(transaction, communication, session=None):
    """Calculate an explainable correlation score from 0 to 1."""

    txn_time = transaction["timestamp_utc"]
    comm_time = communication["timestamp_utc"]
    comm_end = communication.get("end_utc", comm_time)

    if pd.isna(comm_end):
        comm_end = comm_time

    minutes_before = (
        txn_time - comm_end
    ).total_seconds() / 60

    overlap = comm_time <= txn_time <= comm_end
    within_window = (
        0 <= minutes_before <= max(CORRELATION_WINDOWS)
    )

    if not overlap and not within_window:
        return None

    features = {}

    features["temporal_overlap"] = 1.0 if overlap else (
        max(0, 1 - minutes_before / 60)
    )

    duration = 0
    if session is not None:
        duration = max(0, session["duration_hours"])

    features["session_duration"] = min(duration / 8, 1)

    features["new_payee"] = 0.5
    features["amount_anomaly"] = 0.5
    features["repeat_transfer"] = 0.0

    hour = txn_time.hour
    features["night_activity"] = (
        1.0 if hour >= 22 or hour < 6 else 0.0
    )

    amount = transaction.get("amount", 0)
    features["round_amount"] = (
        1.0 if amount > 0 and amount % 1000 == 0 else 0.0
    )

    score = sum(
        features[name] * weight
        for name, weight in FEATURE_WEIGHTS.items()
    )

    return {
        "confidence": round(float(score), 4),
        "features": features,
        "minutes_after_communication": round(
            float(minutes_before), 2
        ),
        "communication_event_id": communication["event_id"],
    }


def find_correlations(events, transactions, sessions):
    """Find communication events temporally associated with transactions."""

    if events.empty or transactions.empty:
        return pd.DataFrame()

    communications = events[
        events["event_type"].isin(["cdr", "ipdr"])
    ].copy()

    if communications.empty:
        return pd.DataFrame()

    results = []

    for _, txn in transactions.iterrows():
        victim = txn["victim_id"]

        victim_comms = communications[
            communications["victim_id"] == victim
        ]

        victim_sessions = (
            sessions[sessions["victim_id"] == victim]
            if not sessions.empty
            else pd.DataFrame()
        )

        for _, comm in victim_comms.iterrows():
            session_match = None

            if not victim_sessions.empty:
                matches = victim_sessions[
                    (victim_sessions["start_utc"] <= txn["timestamp_utc"])
                    & (victim_sessions["end_utc"] >= comm["timestamp_utc"])
                ]

                if not matches.empty:
                    session_match = matches.iloc[0]

            result = score_transaction(
                txn,
                comm,
                session_match
            )

            if result is None:
                continue

            if result["confidence"] < MIN_CONFIDENCE:
                continue

            results.append({
                "correlation_id": f"corr_{len(results)}",
                "transaction_id": txn["transaction_id"],
                "victim_id": victim,
                "amount": float(txn["amount"]),
                "transaction_time_utc": txn["timestamp_utc"].isoformat(),
                "communication_event_id": result["communication_event_id"],
                "communication_type": comm["event_type"],
                "confidence": result["confidence"],
                "time_difference_minutes": result[
                    "minutes_after_communication"
                ],
                "features": result["features"],
                "interpretation": (
                    "Communication overlapped with transaction"
                    if result["minutes_after_communication"] <= 0
                    else "Transaction followed communication within correlation window"
                ),
                "causation_proven": False,
            })

    return pd.DataFrame(results)


def evaluate_correlations(correlations, transactions):
    """Evaluate against investigator-provided is_coerced labels."""

    if correlations.empty or "is_coerced" not in transactions.columns:
        return {
            "available": False,
            "reason": "No investigator labels or no correlations available."
        }

    labels = transactions[
        ["transaction_id", "is_coerced"]
    ].dropna()

    if labels.empty:
        return {
            "available": False,
            "reason": "No valid is_coerced labels found."
        }

    predictions = correlations[
        ["transaction_id", "confidence"]
    ].drop_duplicates("transaction_id")

    merged = labels.merge(
        predictions,
        on="transaction_id",
        how="left"
    )

    merged["confidence"] = merged["confidence"].fillna(0)
    merged["prediction"] = merged["confidence"] >= MIN_CONFIDENCE

    actual = merged["is_coerced"].astype(bool)
    predicted = merged["prediction"].astype(bool)

    tp = int((actual & predicted).sum())
    fp = int((~actual & predicted).sum())
    fn = int((actual & ~predicted).sum())
    tn = int((~actual & ~predicted).sum())

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    accuracy = (
        (tp + tn) / len(merged) if len(merged) else 0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0
    )

    return {
        "available": True,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "labelled_transactions": len(merged),
    }
