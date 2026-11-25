
from fastapi import FastAPI, Query

from .timeline import build_timeline

app = FastAPI(
    title="TrueTrail Timeline API",
    description="Spatiotemporal correlation and timeline reconstruction API",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "TrueTrail Timeline API",
    }


@app.get("/timeline")
def get_timeline(
    victim: str = Query(None),
    min_confidence: float = Query(0.0, ge=0, le=1),
):
    timeline = build_timeline()

    if victim:
        timeline["events"] = [
            event for event in timeline["events"]
            if event.get("victim_id") == victim
        ]

        timeline["transactions"] = [
            txn for txn in timeline["transactions"]
            if txn.get("victim_id") == victim
        ]

        timeline["sessions"] = [
            session for session in timeline["sessions"]
            if session.get("victim_id") == victim
        ]

        timeline["correlations"] = [
            correlation
            for correlation in timeline["correlations"]
            if correlation.get("victim_id") == victim
            and correlation.get("confidence", 0) >= min_confidence
        ]

        timeline["geo_tracks"] = [
            track for track in timeline["geo_tracks"]
            if track.get("victim_id") == victim
        ]

    else:
        timeline["correlations"] = [
            correlation
            for correlation in timeline["correlations"]
            if correlation.get("confidence", 0) >= min_confidence
        ]

    return timeline
