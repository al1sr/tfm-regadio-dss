import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from src.data.extract_siar_history import _date_chunks, extract_siar_history


class FakeSiAR:
    def __init__(self):
        self.calls = []

    def get_data(
        self,
        data_type,
        scope,
        identifiers,
        start_date,
        end_date,
        *,
        calculated=False,
        last_modified=None,
    ):
        self.calls.append((start_date, end_date))
        return [
            {
                "Estacion": identifiers,
                "Fecha": start_date.isoformat(),
                "EtPMon": 4.0,
            },
            {
                "Estacion": identifiers,
                "Fecha": end_date.isoformat(),
                "EtPMon": 5.0,
            },
        ]


class ExtractSiARHistoryTests(unittest.TestCase):
    def test_builds_quota_safe_chunks(self):
        chunks = list(
            _date_chunks(date(2025, 5, 1), date(2025, 9, 30), 90)
        )
        self.assertEqual(
            chunks,
            [
                (date(2025, 5, 1), date(2025, 7, 29)),
                (date(2025, 7, 30), date(2025, 9, 30)),
            ],
        )

    def test_merges_deduplicates_and_waits_between_chunks(self):
        source = FakeSiAR()
        pauses = []
        with tempfile.TemporaryDirectory() as directory:
            output = extract_siar_history(
                start_date=date(2025, 5, 1),
                end_date=date(2025, 9, 30),
                output_root=Path(directory),
                chunk_days=90,
                pause_seconds=60,
                client=source,
                sleep_fn=pauses.append,
                now=datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc),
            )
            document = json.loads(output.path.read_text(encoding="utf-8"))

        self.assertEqual(len(source.calls), 2)
        self.assertEqual(pauses, [60])
        self.assertEqual(document["query"]["chunk_count"], 2)
        self.assertEqual(document["record_count"], 4)


if __name__ == "__main__":
    unittest.main()
