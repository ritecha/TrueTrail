"""
tests/test_pipeline.py - Unit tests for core forensic normalization, disambiguation,
magic-byte detection, extraction, and schema preservation.
Run with: python -m unittest discover -s tests
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detector import detect_file_type
from app.disambiguator import disambiguate_numeric_column, extract_entities_from_text, luhn_valid
from app.extractors.csv_extractor import extract_csv
from app.normalizer import normalize_amount, normalize_ip, normalize_phone, normalize_timestamp
import config


class ForensicCoreTests(unittest.TestCase):
    def test_normalization_rules(self):
        amt, direction = normalize_amount("1,25,000.00 Dr")
        self.assertEqual(str(amt), "125000.00")
        self.assertEqual(direction, "DEBIT")

        self.assertEqual(normalize_phone("09087772990"), "+919087772990")
        self.assertEqual(normalize_phone("919087772990"), "+919087772990")
        self.assertIsNone(normalize_phone("Hidden"))

        dt, orig_tz = normalize_timestamp("15-03-2024 14:22:00 (UTC+5:30)", config.DEVICE["assume_tz"])
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 8)
        self.assertEqual(dt.minute, 52)
        self.assertIn("+5:30", orig_tz or "")

        ip_norm, is_priv, ver = normalize_ip("192.168.1.50")
        self.assertEqual((ip_norm, is_priv, ver), ("192.168.1.50", True, 4))

    def test_9087772990_disambiguation(self):
        cdr_res = disambiguate_numeric_column(
            header="Column_X",
            values=["9087772990", "9876543210", "9087772990", "7012345678"],
            evidence_type="cdr",
            neighbour_headers=["DURATION_SEC", "CALL_TYPE"],
        )
        self.assertEqual(cdr_res.resolved_type, "PHONE")

        amt_res = disambiguate_numeric_column(
            header="Rupees",
            values=["1,250.00", "45,000.50", "899.00", "12,340.00"],
            evidence_type="bank_statement",
            neighbour_headers=["Narration", "Closing Balance"],
        )
        self.assertEqual(amt_res.resolved_type, "AMOUNT")

    def test_unstructured_entity_extraction(self):
        text = "UPI/412345678901/rahul@oksbi/SBIN0001234/call 9087772990 from 203.0.113.45"
        ents = extract_entities_from_text(text, "sample.txt", source_row=1)
        types = {e["entity_type"]: e["extracted_value"] for e in ents}
        self.assertEqual(types.get("VPA"), "rahul@oksbi")
        self.assertEqual(types.get("IFSC"), "SBIN0001234")
        self.assertEqual(types.get("UTR"), "412345678901")
        self.assertEqual(types.get("PHONE"), "9087772990")
        self.assertEqual(types.get("IP"), "203.0.113.45")

    def test_luhn_and_magic_bytes_and_csv_preamble(self):
        self.assertTrue(luhn_valid("490154203237518"))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "renamed.jpg"
            p.write_text("Account Statement\nAccount No: 000123456789\nTxn Date,Narration,Debit,Balance\n15/03/2024,UPI-TEST-a@okicici-ICIC0000123-412345678901,500.00,1000.00\n")
            det = detect_file_type(p, "renamed.jpg")
            self.assertEqual(det.detected_format, "csv")
            self.assertTrue(det.extension_mismatch)

            ext = extract_csv(p)
            self.assertEqual(len(ext.tables), 1)
            self.assertEqual(ext.tables[0].headers, ["Txn Date", "Narration", "Debit", "Balance"])
            self.assertEqual(ext.tables[0].meta_kv.get("Account No"), "000123456789")


if __name__ == "__main__":
    unittest.main()
