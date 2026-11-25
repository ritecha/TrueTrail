"""
extractors/json_extractor.py - JSON & NDJSON extractor (Cellebrite device reports, DNS, VPN, generic logs).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.extractors.base import ExtractedRow, ExtractedTable, RawExtraction


def extract_json(path: Path) -> RawExtraction:
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return RawExtraction(source_format="json", warnings=["Empty JSON file"])

    payload: Any = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Try NDJSON (one JSON object per line)
        items = []
        for idx, line in enumerate(text.splitlines(), start=1):
            ln = line.strip()
            if not ln:
                continue
            try:
                items.append(json.loads(ln))
            except json.JSONDecodeError:
                return RawExtraction(source_format="json", warnings=[f"Invalid JSON at line {idx}"])
        payload = items

    tables: list[ExtractedTable] = []

    # If top-level is a list of dicts, also materialize a table for uniform classification & mapping
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        headers = list({k for obj in payload if isinstance(obj, dict) for k in obj.keys()})
        rows = [
            ExtractedRow(
                row_number=i,
                page=None,
                sheet_name=None,
                values={h: _stringify(obj.get(h)) for h in headers},
            )
            for i, obj in enumerate(payload, start=1)
            if isinstance(obj, dict)
        ]
        tables.append(ExtractedTable(name="json_records", headers=headers, rows=rows))
    elif isinstance(payload, dict):
        # Handle dict containing list of records (e.g. {"records": [...]})
        for key, val in payload.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                headers = list({k for obj in val if isinstance(obj, dict) for k in obj.keys()})
                rows = [
                    ExtractedRow(
                        row_number=i,
                        page=None,
                        sheet_name=key,
                        values={h: _stringify(obj.get(h)) for h in headers},
                    )
                    for i, obj in enumerate(val, start=1)
                    if isinstance(obj, dict)
                ]
                tables.append(ExtractedTable(name=key, headers=headers, rows=rows))

    return RawExtraction(
        source_format="json",
        tables=tables,
        json_payload=payload,
        text_blocks=[{"page": 1, "text": text[:8000], "confidence": 1.0}],
    )


def _stringify(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val).strip()
