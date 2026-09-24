"""Pruebas del proceso de extracción sin consumir las APIs reales."""

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from src.data.extract_pilot import extract_pilot


class FakeSiARClient:
    def get_info(self, information_type):
        return [{"tipo": information_type}]

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
        return [{"Fecha": start_date.isoformat(), "Estacion": identifiers}]


class FakeAEMETClient:
    def get_municipalities(self):
        return [{"id": "id04013", "nombre": "Almería"}]

    def get_climate_stations(self):
        return [{"indicativo": "6325O"}]

    def get_daily_municipality_forecast(self, municipality_code):
        return [{"id": municipality_code, "prediccion": {"dia": [1]}}]

    def get_hourly_municipality_forecast(self, municipality_code):
        return [{"id": municipality_code, "prediccion": {"dia": [1, 2]}}]


class ExtractPilotTests(unittest.TestCase):
    def test_writes_seven_traceable_raw_files_with_catalogs(self):
        fixed_now = datetime(2026, 9, 24, 8, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            outputs = extract_pilot(
                start_date=date(2026, 9, 17),
                end_date=date(2026, 9, 23),
                output_root=Path(directory),
                include_siar_catalogs=True,
                include_aemet_catalogs=True,
                siar_client=FakeSiARClient(),
                aemet_client=FakeAEMETClient(),
                now=fixed_now,
            )

            self.assertEqual(len(outputs), 7)
            self.assertTrue(all(output.path.exists() for output in outputs))
            daily = next(item for item in outputs if item.dataset == "weather_daily")
            envelope = json.loads(daily.path.read_text(encoding="utf-8"))
            self.assertEqual(envelope["source"], "SiAR")
            self.assertEqual(envelope["record_count"], 1)
            self.assertEqual(envelope["query"]["station"], "AL01")
            self.assertNotIn("token", json.dumps(envelope).lower())
            self.assertIn("station=AL01", str(daily.path))

    def test_can_skip_catalogs(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = extract_pilot(
                start_date=date(2026, 9, 23),
                end_date=date(2026, 9, 23),
                output_root=Path(directory),
                siar_client=FakeSiARClient(),
                aemet_client=FakeAEMETClient(),
                now=datetime(2026, 9, 24, tzinfo=timezone.utc),
            )

            self.assertEqual(
                [item.dataset for item in outputs],
                ["weather_daily", "forecast_daily", "forecast_hourly"],
            )

    def test_rejects_invalid_range_and_identifiers(self):
        with self.assertRaisesRegex(ValueError, "fecha inicial"):
            extract_pilot(
                start_date=date(2026, 9, 24),
                end_date=date(2026, 9, 23),
                siar_client=FakeSiARClient(),
                aemet_client=FakeAEMETClient(),
            )

    def test_catalogs_only_avoids_series_and_forecasts(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = extract_pilot(
                start_date=date(2026, 9, 23),
                end_date=date(2026, 9, 23),
                output_root=Path(directory),
                include_aemet_catalogs=True,
                catalogs_only=True,
                siar_client=FakeSiARClient(),
                aemet_client=FakeAEMETClient(),
                now=datetime(2026, 9, 24, tzinfo=timezone.utc),
            )

            self.assertEqual(
                [item.dataset for item in outputs],
                ["municipalities", "climate_stations"],
            )

        with self.assertRaisesRegex(ValueError, "seleccionar"):
            extract_pilot(
                start_date=date(2026, 9, 23),
                end_date=date(2026, 9, 23),
                catalogs_only=True,
                siar_client=FakeSiARClient(),
                aemet_client=FakeAEMETClient(),
            )

        with self.assertRaisesRegex(ValueError, "estación SiAR"):
            extract_pilot(
                start_date=date(2026, 9, 23),
                end_date=date(2026, 9, 23),
                siar_station="../AL01",
                siar_client=FakeSiARClient(),
                aemet_client=FakeAEMETClient(),
            )


if __name__ == "__main__":
    unittest.main()
