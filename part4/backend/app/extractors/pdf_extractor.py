"""
extractors/pdf_extractor.py - Text-based PDF extractor with table reconstruction
and automatic fallback to OCR for scanned / image-only PDF pages.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.extractors.base import ExtractedRow, ExtractedTable, RawExtraction
from app.extractors.ocr_extractor import extract_scanned_pdf


def extract_pdf(path: Path) -> RawExtraction:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required to parse PDF files (pip install pdfplumber)") from exc

    tables: list[ExtractedTable] = []
    text_blocks: list[dict[str, Any]] = []
    scanned_pages: list[int] = []
    warnings: list[str] = []

    with pdfplumber.open(str(path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            page_tables = page.extract_tables() or []

            if len(page_text) < 25 and not page_tables:
                scanned_pages.append(page_idx)
                continue

            if page_text:
                text_blocks.append({"page": page_idx, "text": page_text, "confidence": 1.0})

            for t_idx, raw_table in enumerate(page_tables):
                cleaned_rows = [
                    [(cell or "").replace("\n", " ").strip() for cell in row]
                    for row in raw_table
                    if row and any((c or "").strip() for c in row)
                ]
                if len(cleaned_rows) < 2:
                    continue

                raw_headers = cleaned_rows[0]
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
                for r_idx, r in enumerate(cleaned_rows[1:], start=2):
                    if r[: len(raw_headers)] == raw_headers:
                        continue
                    values = {col: (r[i] if i < len(r) else "") for i, col in enumerate(headers)}
                    extracted_rows.append(
                        ExtractedRow(
                            row_number=r_idx,
                            page=page_idx,
                            sheet_name=None,
                            values=values,
                            raw_cells=r,
                        )
                    )

                tables.append(
                    ExtractedTable(
                        name=f"pdf_p{page_idx}_t{t_idx+1}",
                        headers=headers,
                        rows=extracted_rows,
                        metadata_lines=page_text.splitlines()[:10] if page_text else [],
                    )
                )

    ocr_used = False
    ocr_conf = None
    if scanned_pages:
        try:
            ocr_res = extract_scanned_pdf(path, page_numbers=scanned_pages)
            text_blocks.extend(ocr_res.text_blocks)
            ocr_used = True
            ocr_conf = ocr_res.ocr_confidence
            warnings.append(f"OCR applied to scanned PDF pages: {scanned_pages}")
        except RuntimeError as exc:
            warnings.append(f"Scanned PDF pages {scanned_pages} detected, OCR unavailable: {exc}")

    text_blocks.sort(key=lambda b: b.get("page", 0))
    return RawExtraction(
        source_format="scanned_pdf" if (ocr_used and not tables) else "pdf",
        tables=tables,
        text_blocks=text_blocks,
        ocr_used=ocr_used,
        ocr_confidence=ocr_conf,
        warnings=warnings,
    )
