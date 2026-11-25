"""
routes/correlate.py - Cross-evidence correlation endpoints for frontend investigators.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from app.correlation import (
    correlate_by_entity,
    get_entity_graph,
    get_rrn_corroborations,
    get_shared_entities,
    get_unified_timeline,
)
from app.db import get_db

router = APIRouter(prefix="/api/v1/correlate", tags=["Correlation"])


@router.get("/entity/{value}")
def lookup_entity_correlation(value: str):
    """Find all normalized events and evidence files mentioning a phone, VPA, account, IP, IMEI, RRN, etc."""
    return correlate_by_entity(get_db(), value)


@router.get("/shared-entities")
def list_shared_entities(min_files: int = 2):
    """Find identifiers that appear across multiple distinct evidence files."""
    items = get_shared_entities(get_db(), min_files=min_files)
    return {"count": len(items), "items": items}


@router.get("/timeline")
def timeline(
    evidence_id: Optional[str] = None,
    event_type: Optional[str] = None,
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    return get_unified_timeline(
        get_db(),
        evidence_id=evidence_id,
        event_type=event_type,
        start_utc=start_utc,
        end_utc=end_utc,
        limit=limit,
        offset=offset,
    )


@router.get("/graph")
def entity_graph(limit_links: int = 300):
    return get_entity_graph(get_db(), limit_links=limit_links)


@router.get("/rrn-matches")
def rrn_matches():
    """Returns transactions linked across UPI logs and Bank Statements via 12-digit RRN."""
    items = get_rrn_corroborations(get_db())
    return {"count": len(items), "items": items}
