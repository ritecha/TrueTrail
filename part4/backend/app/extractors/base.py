"""
extractors/base.py - Common raw extraction data structures (Stage 3 output, zero interpretation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExtractedRow:
    row_number: int                 # 1-based original line/row index
    page: Optional[int]             # 1-based PDF page or None
    sheet_name: Optional[str]       # Excel sheet name or None
    values: dict[str, str]          # column_name -> raw string value
    raw_cells: list[str] = field(default_factory=list)


@dataclass
class ExtractedTable:
    name: str
    headers: list[str]
    rows: list[ExtractedRow]
    metadata_lines: list[str] = field(default_factory=list)
    meta_kv: dict[str, str] = field(default_factory=dict)
    sheet_hidden: bool = False


@dataclass
class RawExtraction:
    source_format: str              # csv | xlsx | pdf | scanned_pdf | image | json
    tables: list[ExtractedTable] = field(default_factory=list)
    text_blocks: list[dict[str, Any]] = field(default_factory=list)  # {page, text, confidence}
    json_payload: Any = None
    ocr_used: bool = False
    ocr_confidence: Optional[float] = None
    warnings: list[str] = field(default_factory=list)
