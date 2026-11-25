"""
detector.py - Stage 2: Magic-byte file type detection & integrity screening.
Never trusts filename/extension alone; detects renamed, encrypted, or corrupted files.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DetectionResult:
    detected_format: str            # pdf | xlsx | xls | csv | json | jpeg | png | unknown
    extension: str
    extension_mismatch: bool
    is_encrypted: bool
    is_corrupted: bool
    error_reason: Optional[str] = None


def detect_file_type(path: Path, original_filename: str) -> DetectionResult:
    ext = Path(original_filename).suffix.lower().lstrip(".")
    head = path.read_bytes()[:4096]

    if not head:
        return DetectionResult("unknown", ext, False, False, True, "Empty file")

    # 1. PDF
    if head.startswith(b"%PDF-"):
        raw_all = path.read_bytes()
        is_encrypted = b"/Encrypt" in raw_all
        if b"%%EOF" not in raw_all[-2048:] and len(raw_all) > 64:
            # Some PDFs lack trailing EOF or have trailing whitespace; still warn only if unreadable later
            pass
        return DetectionResult(
            detected_format="pdf",
            extension=ext,
            extension_mismatch=(ext not in {"pdf", ""}),
            is_encrypted=is_encrypted,
            is_corrupted=False,
            error_reason="Password-protected/encrypted PDF" if is_encrypted else None,
        )

    # 2. PNG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectionResult("png", ext, ext not in {"png", ""}, False, False)

    # 3. JPEG
    if head.startswith(b"\xff\xd8\xff"):
        return DetectionResult("jpeg", ext, ext not in {"jpg", "jpeg", ""}, False, False)

    # 4. ZIP / XLSX (OOXML)
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        try:
            with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as zf:
                names = set(zf.namelist())
                if any(n.startswith("xl/") for n in names) or "[Content_Types].xml" in names:
                    return DetectionResult("xlsx", ext, ext not in {"xlsx", "xlsm", ""}, False, False)
                if "EncryptedPackage" in names:
                    return DetectionResult("xlsx", ext, False, True, False, "Encrypted XLSX workbook")
                return DetectionResult("zip", ext, ext not in {"zip", ""}, False, False, "Unsupported archive (not XLSX)")
        except zipfile.BadZipFile:
            return DetectionResult("xlsx", ext, False, False, True, "Corrupted ZIP/XLSX container")

    # 5. Legacy OLE2 (.xls) or encrypted Office
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return DetectionResult("xls", ext, ext not in {"xls", ""}, False, False, "Legacy binary .xls detected; convert to .xlsx or CSV")

    # 6. UTF-8/UTF-16 Text / JSON / CSV / TSV / Pipe
    text_sample = _decode_sample(head)
    if text_sample is None:
        return DetectionResult("unknown", ext, True, False, True, "Unrecognized binary file signature")

    stripped = text_sample.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
            return DetectionResult("json", ext, ext not in {"json", "ndjson", "log", "txt", ""}, False, False)
        except Exception:
            # Might be NDJSON (newline-delimited JSON)
            lines = [ln.strip() for ln in path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if ln.strip()]
            if lines and _is_json_line(lines[0]):
                return DetectionResult("json", ext, ext not in {"json", "ndjson", "log", "txt", ""}, False, False)

    return DetectionResult("csv", ext, ext not in {"csv", "tsv", "txt", "log", ""}, False, False)


def _decode_sample(head: bytes) -> Optional[str]:
    if b"\x00" in head[:256] and not (head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff")):
        return None
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return head.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _is_json_line(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except Exception:
        return False
