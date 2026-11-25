"""
correlation.py - Cross-evidence correlation engine.
Finds shared identifiers across evidence files, reconstructs unified UTC timelines,
computes entity-event graphs, and lists UPI <-> Bank Statement RRN corroborations.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.db import ForensicDB
from app.normalizer import normalize_ip, normalize_phone


def _candidate_lookup_values(query: str) -> list[str]:
    q = query.strip()
    vals = {q, q.upper(), q.lower()}
    phone = normalize_phone(q)
    if phone:
        vals.add(phone)
    ip_norm, _, _ = normalize_ip(q)
    if ip_norm:
        vals.add(ip_norm)
    return [v for v in vals if v]


def correlate_by_entity(db: ForensicDB, query: str) -> dict[str, Any]:
    candidates = _candidate_lookup_values(query)
    placeholders = ",".join("?" for _ in candidates)
    entities = db.fetch_all(
        f"SELECT * FROM canonical_entities WHERE normalized_value IN ({placeholders})",
        tuple(candidates),
    )
    if not entities:
        return {"query": query, "entities": [], "events": [], "evidence_files": []}

    ent_ids = [e["entity_id"] for e in entities]
    ep = ",".join("?" for _ in ent_ids)
    events = db.fetch_all(
        f"""
        SELECT DISTINCT ne.*, eel.role, eel.confidence AS link_confidence
        FROM entity_event_links eel
        JOIN normalized_events ne ON ne.event_id = eel.event_id
        WHERE eel.entity_id IN ({ep})
        ORDER BY ne.timestamp ASC
        """,
        tuple(ent_ids),
    )
    for ev in events:
        ev["attributes"] = json.loads(ev.pop("attributes_json", "{}"))
    for ent in entities:
        ent["raw_examples"] = json.loads(ent.pop("raw_examples_json", "[]"))

    files = sorted({ev["source_file"] for ev in events})
    return {
        "query": query,
        "entities": entities,
        "event_count": len(events),
        "evidence_files": files,
        "events": events,
    }


def get_unified_timeline(
    db: ForensicDB,
    evidence_id: Optional[str] = None,
    event_type: Optional[str] = None,
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    clauses = ["1=1"]
    params: list[Any] = []
    if evidence_id:
        clauses.append("evidence_id = ?")
        params.append(evidence_id)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if start_utc:
        clauses.append("timestamp >= ?")
        params.append(start_utc)
    if end_utc:
        clauses.append("timestamp <= ?")
        params.append(end_utc)

    where_sql = " AND ".join(clauses)
    rows = db.fetch_all(
        f"""
        SELECT * FROM normalized_events
        WHERE {where_sql}
        ORDER BY timestamp ASC
        LIMIT ? OFFSET ?
        """,
        tuple([*params, limit, offset]),
    )
    for r in rows:
        r["attributes"] = json.loads(r.pop("attributes_json", "{}"))
    return {"count": len(rows), "events": rows}


def get_shared_entities(db: ForensicDB, min_files: int = 2) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT ce.entity_id, ce.entity_type, ce.normalized_value, ce.raw_examples_json,
               COUNT(DISTINCT eel.source_file) AS file_count,
               GROUP_CONCAT(DISTINCT eel.source_file) AS files,
               COUNT(DISTINCT eel.event_id) AS event_count
        FROM canonical_entities ce
        JOIN entity_event_links eel ON eel.entity_id = ce.entity_id
        GROUP BY ce.entity_id
        HAVING file_count >= ?
        ORDER BY file_count DESC, event_count DESC
        """,
        (min_files,),
    )
    for r in rows:
        r["raw_examples"] = json.loads(r.pop("raw_examples_json", "[]"))
        r["files"] = [f for f in (r["files"] or "").split(",") if f]
    return rows


def get_entity_graph(db: ForensicDB, limit_links: int = 300) -> dict[str, Any]:
    links = db.fetch_all(
        """
        SELECT eel.link_id, eel.entity_id, eel.event_id, eel.role, eel.confidence, eel.source_file,
               ce.entity_type, ce.normalized_value,
               ne.event_type, ne.timestamp, ne.amount
        FROM entity_event_links eel
        JOIN canonical_entities ce ON ce.entity_id = eel.entity_id
        JOIN normalized_events ne ON ne.event_id = eel.event_id
        LIMIT ?
        """,
        (limit_links,),
    )
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for lnk in links:
        ent_node = lnk["entity_id"]
        evt_node = lnk["event_id"]
        if ent_node not in nodes:
            nodes[ent_node] = {
                "id": ent_node,
                "kind": "ENTITY",
                "type": lnk["entity_type"],
                "label": lnk["normalized_value"],
            }
        if evt_node not in nodes:
            nodes[evt_node] = {
                "id": evt_node,
                "kind": "EVENT",
                "type": lnk["event_type"],
                "label": f"{lnk['event_type']} ({lnk['timestamp'] or 'n/a'})",
                "amount": lnk["amount"],
                "source_file": lnk["source_file"],
            }
        edges.append({
            "id": lnk["link_id"],
            "source": ent_node,
            "target": evt_node,
            "role": lnk["role"],
            "confidence": lnk["confidence"],
        })
    return {"nodes": list(nodes.values()), "edges": edges}


def get_rrn_corroborations(db: ForensicDB) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT rrn, payload_json
        FROM transactions
        WHERE rrn IS NOT NULL AND rrn != ''
        ORDER BY timestamp ASC
        """
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        grouped.setdefault(r["rrn"], []).append(json.loads(r["payload_json"]))

    matches = []
    for rrn, items in grouped.items():
        source_types = {it["source_type"] for it in items}
        if len(source_types) > 1 or len(items) > 1:
            matches.append({
                "rrn": rrn,
                "cross_source_corroborated": len(source_types) > 1,
                "records": items,
            })
    return matches
