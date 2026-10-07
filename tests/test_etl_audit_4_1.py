"""Pruebas del resumen reproducible de volumen y calidad de la ETL."""

import csv
import tempfile
import unittest
from pathlib import Path

from src.analysis.build_etl_audit_4_1 import (
    _duplicate_count,
    _missing_date_count,
    _quality_counts,
    write_audit,
)


class EtlAuditTests(unittest.TestCase):
    def test_quality_duplicates_and_calendar_gaps(self):
        rows = [
            {"station_code": "AL01", "observed_date": "2025-05-01", "quality_status": "PASS"},
            {"station_code": "AL01", "observed_date": "2025-05-03", "quality_status": "WARN"},
            {"station_code": "AL01", "observed_date": "2025-05-03", "quality_status": "WARN"},
        ]

        self.assertEqual(_quality_counts(rows), (1, 2))
        self.assertEqual(_duplicate_count(rows, ("station_code", "observed_date")), 1)
        self.assertEqual(_missing_date_count(rows, "observed_date"), 1)

    def test_write_audit_preserves_output_columns(self):
        row = {
            "stage": "processed",
            "dataset": "modeling_dataset_daily",
            "source": "SiAR integrado",
            "rows": 150,
            "columns": 88,
            "valid_target_rows": 148,
            "pass_rows": 148,
            "warning_rows": 2,
            "duplicate_rows": 0,
            "missing_calendar_dates": 3,
            "file_size_bytes": 132990,
            "notes": "Piloto",
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "audit.csv"
            write_audit([row], output)
            with output.open("r", encoding="utf-8-sig", newline="") as stream:
                written = list(csv.DictReader(stream))

        self.assertEqual(written[0]["rows"], "150")
        self.assertEqual(written[0]["valid_target_rows"], "148")


if __name__ == "__main__":
    unittest.main()
