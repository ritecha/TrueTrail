
import pandas as pd

from .timeutil import haversine_distance


def build_geo_track(events):
    """Build movement track using tower ping coordinates."""

    if events.empty:
        return []

    pings = events[
        (events["event_type"] == "ping")
        & events["latitude"].notna()
        & events["longitude"].notna()
    ].copy()

    if pings.empty:
        return []

    tracks = []

    for victim, group in pings.groupby("victim_id"):
        group = group.sort_values("timestamp_utc")

        points = []

        previous = None

        for _, row in group.iterrows():
            point = {
                "timestamp": row["timestamp_utc"].isoformat(),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "tower_id": row.get("tower_id"),
            }

            if previous is not None:
                distance = haversine_distance(
                    previous["latitude"],
                    previous["longitude"],
                    point["latitude"],
                    point["longitude"],
                )

                time_hours = (
                    pd.Timestamp(point["timestamp"])
                    - pd.Timestamp(previous["timestamp"])
                ).total_seconds() / 3600

                speed = (
                    distance / 1000 / time_hours
                    if time_hours > 0 else None
                )

                point["distance_from_previous_m"] = round(distance, 2)
                point["estimated_speed_kmph"] = (
                    round(speed, 2) if speed is not None else None
                )
                point["impossible_speed"] = (
                    speed is not None and speed > 120
                )

            points.append(point)
            previous = point

        tracks.append({
            "victim_id": victim,
            "point_count": len(points),
            "points": points,
        })

    return tracks


def tower_coverage_geojson(towers):
    """Create GeoJSON point features for tower locations."""

    features = []

    if towers.empty:
        return {
            "type": "FeatureCollection",
            "features": [],
        }

    for _, row in towers.iterrows():
        features.append({
            "type": "Feature",
            "properties": {
                "tower_id": str(row["tower_id"]),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [
                    float(row["longitude"]),
                    float(row["latitude"]),
                ],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def proximity_checks(events, sessions):
    """Compare communication session times with available tower pings."""

    results = []

    if events.empty or sessions.empty:
        return results

    pings = events[
        events["event_type"] == "ping"
    ].copy()

    for _, session in sessions.iterrows():
        victim_pings = pings[
            pings["victim_id"] == session["victim_id"]
        ]

        matching = victim_pings[
            (victim_pings["timestamp_utc"] >= session["start_utc"])
            & (victim_pings["timestamp_utc"] <= session["end_utc"])
        ]

        results.append({
            "session_id": session["session_id"],
            "victim_id": session["victim_id"],
            "session_start": session["start_utc"].isoformat(),
            "session_end": session["end_utc"].isoformat(),
            "tower_pings_during_session": len(matching),
            "has_location_evidence": not matching.empty,
        })

    return results
