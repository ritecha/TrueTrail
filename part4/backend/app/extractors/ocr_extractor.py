"""
extractors/ocr_extractor.py - OCR extractor for JPEG, PNG, and scanned PDFs.
Applies image preprocessing (grayscale, contrast enhancement, sharpening) and
records per-page Tesseract confidence scores (OCR values always carry confidence < 1.0).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.extractors.base import RawExtraction


def _preprocess_image(img: Any) -> Any:
    from PIL import ImageEnhance, ImageFilter, ImageOps

    img = ImageOps.exif_transpose(img)
    gray = ImageOps.grayscale(img)
    # Upscale low-res screenshots/scans to improve OCR accuracy
    w, h = gray.size
    if w < 1400:
        scale = min(2.0, 1400.0 / max(w, 1))
        gray = gray.resize((int(w * scale), int(h * scale)))
    gray = ImageOps.autocontrast(gray)
    gray = ImageEnhance.Contrast(gray).enhance(1.4)
    gray = gray.filter(ImageFilter.SHARPEN)
    return gray


def _ocr_pil_image(img: Any) -> tuple[str, float]:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError(
            "pytesseract and Pillow are required for OCR (pip install pytesseract pillow)"
        ) from exc

    cleaned = _preprocess_image(img)
    data = pytesseract.image_to_data(cleaned, output_type=Output.DICT)
    words: list[str] = []
    confs: list[float] = []
    lines_map: dict[tuple[int, int, int], list[str]] = {}

    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        conf_raw = str(data["conf"][i])
        try:
            conf_val = float(conf_raw)
        except ValueError:
            conf_val = -1.0
        if txt:
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines_map.setdefault(key, []).append(txt)
            words.append(txt)
            if conf_val >= 0:
                confs.append(min(99.0, conf_val) / 100.0)

    ordered_lines = [" ".join(lines_map[k]) for k in sorted(lines_map.keys())]
    text = "\n".join(ordered_lines) if ordered_lines else pytesseract.image_to_string(cleaned)
    mean_conf = round(sum(confs) / len(confs), 3) if confs else 0.50
    return text.strip(), min(0.98, mean_conf)


def extract_image(path: Path) -> RawExtraction:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to read images (pip install pillow)") from exc

    with Image.open(path) as img:
        text, conf = _ocr_pil_image(img)

    return RawExtraction(
        source_format="image",
        text_blocks=[{"page": 1, "text": text, "confidence": conf}],
        ocr_used=True,
        ocr_confidence=conf,
    )


def extract_scanned_pdf(path: Path, page_numbers: list[int] | None = None) -> RawExtraction:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError(
            "pypdfium2 is required to rasterize scanned PDFs for OCR (pip install pypdfium2)"
        ) from exc

    pdf = pdfium.PdfDocument(str(path))
    target_pages = page_numbers if page_numbers is not None else list(range(1, len(pdf) + 1))
    blocks: list[dict[str, Any]] = []
    confs: list[float] = []

    for pno in target_pages:
        page = pdf[pno - 1]
        bitmap = page.render(scale=2.0)
        pil_img = bitmap.to_pil()
        text, conf = _ocr_pil_image(pil_img)
        blocks.append({"page": pno, "text": text, "confidence": conf})
        confs.append(conf)

    avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.50
    return RawExtraction(
        source_format="scanned_pdf",
        text_blocks=blocks,
        ocr_used=True,
        ocr_confidence=avg_conf,
    )
