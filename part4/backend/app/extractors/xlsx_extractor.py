"""
extractors/xlsx_extractor.py - Excel (.xlsx) extractor.
Handles multiple sheets, hidden sheets, merged cells, header rows on arbitrary rows,
and prevents scientific notation / leading-zero loss on identifiers.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.extractors.base import ExtractedRow, ExtractedTable, RawExtraction


def _cell_to_text(val: Any, number_format: str = "") -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        # Avoid scientific notation on long integer IDs (account nos, IMEIs, phone numbers)
        if val.is_integer() and abs(val) >= 1e6:
            return str(Decimal(str(val)).quantize(Decimal("1")))
        return format(val, "g") if "e" not in str(val).lower() else format(Decimal(str(val)), "f").rstrip("0").rstrip(".")
    return str(val).strip()


def _detect_header_row(grid: list[list[str]]) -> int:
    max_non_empty = max((sum(1 for c in row if c) for row in grid[:35]), default=0)
    if max_non_empty <= 1:
        return 0
    for idx, row in enumerate(grid[:35]):
        non_empty = [c for c in row if c]
        if len(non_empty) >= max(2, int(max_non_empty * 0.65)):
            numeric_like = sum(1 for c in non_empty if re.fullmatch(r"[\d,.\-+]+", c))
            if numeric_like <= len(non_empty) // 2:
                return idx
    return 0


def extract_xlsx(path: Path) -> RawExtraction:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to parse .xlsx files (pip install openpyxl)") from exc

    wb = openpyxl.load_workbook(filename=str(path), data_only=True, read_only=False)
    tables: list[ExtractedTable] = []
    warnings: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        is_hidden = ws.sheet_state != "visible"
        if is_hidden:
            warnings.append(f"Hidden sheet detected and inspected: {sheet_name}")

        # Build merged-cell lookup so top-left value propagates cleanly across merged headers/cells
        merged_values: dict[tuple[int, int], Any] = {}
        for m_range in ws.merged_cells.ranges:
            top_left_val = ws.cell(m_range.min_row, m_range.min_col).value
            for r in range(m_range.min_row, m_range.max_row + 1):
                for c in range(m_range.min_col, m_range.max_col + 1):
                    merged_values[(r, c)] = top_left_val

        grid_with_row_idx: list[tuple[int, list[str]]] = []
        for r_idx in range(1, ws.max_row + 1):
            row_vals: list[str] = []
            for c_idx in range(1, ws.max_column + 1):
                cell = ws.cell(r_idx, c_idx)
                raw_val = merged_values.get((r_idx, c_idx), cell.value)
                txt = _cell_to_text(raw_val, getattr(cell, "number_format", ""))
                row_vals.append(txt)
            if any(row_vals):
                grid_with_row_idx.append((r_idx, row_vals))

        if not grid_with_row_idx:
            continue

        just_grid = [r for _, r in grid_with_row_idx]
        hdr_pos = _detect_header_row(just_grid)

        metadata_lines: list[str] = []
        meta_kv: dict[str, str] = {}
        for _, pre_row in grid_with_row_idx[:hdr_pos]:
            non_empty = [c for c in pre_row if c]
            if non_empty:
                metadata_lines.append(" | ".join(non_empty))
            if len(non_empty) >= 2:
                meta_kv[non_empty[0].rstrip(":")] = non_empty[1]
            elif len(non_empty) == 1 and ":" in non_empty[0]:
                k, _, v = non_empty[0].partition(":")
                if k.strip() and v.strip():
                    meta_kv[k.strip()] = v.strip()

        raw_headers = just_grid[hdr_pos]
        # Trim trailing empty columns
        last_non_empty = max((i for i, h in enumerate(raw_headers) if h), default=len(raw_headers) - 1)
        raw_headers = raw_headers[: last_non_empty + 1]

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
        for orig_row_no, row in grid_with_row_idx[hdr_pos + 1:]:
            values = {col: (row[i] if i < len(row) else "") for i, col in enumerate(headers)}
            if not any(values.values()):
                continue
            extracted_rows.append(
                ExtractedRow(
                    row_number=orig_row_no,
                    page=None,
                    sheet_name=sheet_name,
                    values=values,
                    raw_cells=row[: len(headers)],
                )
            )

        tables.append(
            ExtractedTable(
                name=sheet_name,
                headers=headers,
                rows=extracted_rows,
                metadata_lines=metadata_lines,
                meta_kv=meta_kv,
                sheet_hidden=is_hidden,
            )
        )

    wb.close()
    return RawExtraction(source_format="xlsx", tables=tables, warnings=warnings)
