
import math
import pandas as pd

from .config import SOURCE_TIMEZONE


def to_utc(value):
    """Convert source timestamp to UTC."""
    if pd.isna(value):
        return pd.NaT

    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(
            SOURCE_TIMEZONE,
            ambiguous="NaT",
            nonexistent="shift_forward"
        )

    return timestamp.tz_convert("UTC")


def format_utc(value):
    """Return timestamp in ISO-8601 UTC format."""
    if pd.isna(value):
        return None

    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")

    return timestamp.isoformat()


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two geographic points in meters."""
    earth_radius = 6371000

    lat1, lon1, lat2, lon2 = map(
        math.radians,
        [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * earth_radius * math.asin(math.sqrt(a))
