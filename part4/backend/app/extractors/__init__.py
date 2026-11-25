"""
extractors/__init__.py - Format extractor plugin dispatcher (Stage 3).
"""
from __future__ import annotations

from pathlib import Path

from app.extractors.base import RawExtraction
from app.extractors.csv_extractor import extract_csv
from app.extractors.json_extractor import extract_json
from app.extractors.ocr_extractor import extract_image
from app.extractors.pdf_extractor import extract_pdf
from app.extractors.xlsx_extractor import extract_xlsx


EXTRACTORS = {
    "csv": extract_csv,
    "xlsx": extract_xlsx,
    "json": extract_json,
    "pdf": extract_pdf,
    "jpeg": extract_image,
    "png": extract_image,
}


def run_extractor(detected_format: str, path: Path) -> RawExtraction:
    extractor = EXTRACTORS.get(detected_format)
    if extractor is None:
        raise ValueError(f"No extractor plugin registered for format '{detected_format}'")
    return extractor(path)
