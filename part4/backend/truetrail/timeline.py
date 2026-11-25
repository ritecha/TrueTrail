
import json
from pathlib import Path

from . import config
from .loaders import load_all
from .sessions import build_sessions
from .correlate import find_correlations, evaluate_correlations
from .geo import (
    build_geo_track,
    tower_coverage_geojson,
    proximity_checks,
)


def safe_records(dataframe):
    """Convert DataFrame into JSON-safe records."""

    if dataframe is None or dataframe.empty:
        return []

    return json.loads(
        dataframe.to_json(
            orient="records",
            date_format="iso"
        )
    )


def build_timeline():
    """Run the complete TrueTrail analysis pipeline."""

    data = load_all()

    events = data["events"]
    transactions = data["transactions"]
    towers = data["towers"]

    sessions = build_sessions(events)

    correlations = find_correlations(
        events,
        transactions,
        sessions
    )

    geo_tracks = build_geo_track(events)

    proximity = proximity_checks(
        events,
        sessions
    )

    evaluation = evaluate_correlations(
        correlations,
        transactions
    )

    timeline = {
        "project": "TrueTrail",
        "version": config.API_VERSION,
        "timezone": "UTC",
        "summary": {
            "total_events": len(events),
            "total_transactions": len(transactions),
            "total_sessions": len(sessions),
            "total_correlations": len(correlations),
            "total_geo_tracks": len(geo_tracks),
        },
        "events": safe_records(events),
        "transactions": safe_records(transactions),
        "sessions": safe_records(sessions),
        "correlations": safe_records(correlations),
        "geo_tracks": geo_tracks,
        "proximity_checks": proximity,
        "tower_coverage": tower_coverage_geojson(towers),
        "evaluation": evaluation,
        "assumptions": config.ASSUMPTIONS,
        "disclaimer": (
            "Temporal correlation does not establish causation. "
            "All results require human investigation and verification."
        ),
    }

    return timeline


def save_timeline(timeline, output_path=None):
    """Save timeline JSON."""

    path = Path(output_path or config.TIMELINE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            timeline,
            file,
            indent=4,
            ensure_ascii=False,
            default=str
        )

    return path
