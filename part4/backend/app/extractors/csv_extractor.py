"""
extractors/csv_extractor.py - CSV / TSV / Pipe-delimited / TXT log extractor.
Handles encodings, delimiter sniffing, junk preamble lines, and key:value header blocks.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from app.extractors.base import ExtractedRow, ExtractedTable, RawExtraction


_CANDIDATE_DELIMITERS = [",", "\t", "|", ";"]


def _decode_file(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def _detect_delimiter(lines: list[str]) -> str:
    non_empty = [ln for ln in lines[:40] if ln.strip()]
    if not non_empty:
        return ","
    best_delim = ","
    best_score = -1.0
    for delim in _CANDIDATE_DELIMITERS:
        counts = [ln.count(delim) for ln in non_empty]
        # Prefer delimiter that appears consistently across multiple lines with >= 2 columns
        multi = [c for c in counts if c >= 1]
        if len(multi) < max(1, len(non_empty) // 4):
            continue
        avg = sum(multi) / len(multi)
        variance = sum((c - avg) ** 2 for c in multi) / len(multi)
        score = len(multi) * avg / (1.0 + variance)
        if score > best_score:
            best_score = score
            best_delim = delim
    return best_delim


def _find_header_index(rows: list[list[str]]) -> int:
    """
    Skip junk/title lines above the real table header.
    Finds the first row that matches the modal column width (>= 2 non-empty text cells).
    """
    widths = [sum(1 for c in r if c.strip()) for r in rows[:30]]
    if not widths:
        return 0
    max_w = max(widths)
    if max_w <= 1:
        return 0
    for idx, r in enumerate(rows[:30]):
        non_empty = [c.strip() for c in r if c.strip()]
        if len(non_empty) >= max(2, int(max_w * 0.7)):
            # Header rows are mostly non-numeric labels
            numeric_like = sum(1 for c in non_empty if re.fullmatch(r"[\d,.\-+]+", c))
            if numeric_like <= len(non_empty) // 2:
                return idx
    return 0


def extract_csv(path: Path) -> RawExtraction:
    text, encoding = _decode_file(path)
    lines = text.splitlines()
    warnings: list[str] = []
    if encoding == "utf-8-replace":
        warnings.append("File contained invalid byte sequences; decoded with replacement characters")

    # Check if unstructured text log (e.g. DNS zone / complaint / key-value TXT) vs tabular
    delim = _detect_delimiter(lines)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    raw_rows = [row for row in reader]

    non_empty_rows = [(i + 1, r) for i, r in enumerate(raw_rows) if any(cell.strip() for cell in r)]
    if not non_empty_rows:
        return RawExtraction(source_format="csv", text_blocks=[{"page": 1, "text": text, "confidence": 1.0}], warnings=warnings)

    just_rows = [r for _, r in non_empty_rows]
    # If mostly 1-column text, treat as text_blocks (e.g. TXT complaint/DNS log)
    multi_col = sum(1 for r in just_rows[:20] if sum(1 for c in r if c.strip()) >= 2)
    if multi_col < 2:
        return RawExtraction(
            source_format="csv",
            text_blocks=[{"page": 1, "text": text, "confidence": 1.0}],
            warnings=warnings,
        )

    hdr_pos = _find_header_index(just_rows)
    metadata_lines: list[str] = []
    meta_kv: dict[str, str] = {}
    for _, pre_row in non_empty_rows[:hdr_pos]:
        joined = " ".join(c.strip() for c in pre_row if c.strip())
        if joined:
            metadata_lines.append(joined)
        if len(pre_row) >= 2 and pre_row[0].strip() and pre_row[1].strip():
            meta_kv[pre_row[0].strip().rstrip(":")] = pre_row[1].strip()
        elif ":" in joined:
            k, _, v = joined.partition(":")
            if k.strip() and v.strip():
                meta_kv[k.strip()] = v.strip()

    raw_headers = [c.strip() for c in just_rows[hdr_pos]]
    headers: list[str] = []
    seen: dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        col = h if h else f"col_{i+1}"
        if col in seen:
            seen[col] += 1
            col = f"{col}_{seen[col]}"
        else:
            seen[col] = 0
        headers.append(col)

    extracted_rows: list[ExtractedRow] = []
    for orig_line_no, row in non_empty_rows[hdr_pos + 1:]:
        # Skip repeated header rows inside CSV dumps
        cleaned = [c.strip() for c in row]
        if cleaned[: len(raw_headers)] == raw_headers:
            continue
        values: dict[str, str] = {}
        for idx, col in enumerate(headers):
            values[col] = row[idx].strip() if idx < len(row) else ""
        extracted_rows.append(
            ExtractedRow(
                row_number=orig_line_no,
                page=None,
                sheet_name=None,
                values=values,
                raw_cells=[str(c) for c in row],
            )
        )

    table = ExtractedTable(
        name="csv_table",
        headers=headers,
        rows=extracted_rows,
        metadata_lines=metadata_lines,
        meta_kv=meta_kv,
    )
    return RawExtraction(
        source_format="csv",
        tables=[table],
        text_blocks=[{"page": 1, "text": "\n".join(metadata_lines), "confidence": 1.0}] if metadata_lines else [],
        warnings=warnings,
    )
