"""Pruebas de normalización de las tablas interim."""

import unittest

from src.data.transform_interim import (
    _calendar_gaps,
    normalize_aemet_daily,
    normalize_aemet_hourly,
    normalize_siar_crop_needs,
    normalize_siar_daily,
)


class TransformInterimTests(unittest.TestCase):
    def test_detects_missing_calendar_dates(self):
        rows = [
            {"observed_date": "2025-07-17"},
            {"observed_date": "2025-07-21"},
        ]
        self.assertEqual(
            _calendar_gaps(rows),
            ["2025-07-18", "2025-07-19", "2025-07-20"],
        )

    def test_normalizes_crop_water_needs_and_flags_missing_weather(self):
        rows = normalize_siar_crop_needs(
            [
                {
                    "Fecha": "01/05/2025",
                    "Kc": "0,50",
                    "ET0 (mm)": "4,72",
                    "ETc (mm)": "2,36",
                    "Pe (mm)": "0,00",
                    "ETc - Pe (mm)": "2,36",
                },
                {
                    "Fecha": "21/07/2025",
                    "Kc": "0,90",
                    "ET0 (mm)": "",
                    "ETc (mm)": "",
                    "Pe (mm)": "",
                    "ETc - Pe (mm)": "",
                },
            ],
            metadata={
                "station_code": "AL01",
                "station_name": "La Mojonera",
                "region": "Dalias",
                "crop": "Pimiento",
                "retrieved_at": "2026-09-24",
            },
            source_file="needs.csv",
        )

        self.assertEqual(rows[0]["observed_date"], "2025-05-01")
        self.assertEqual(rows[0]["quality_status"], "PASS")
        self.assertEqual(rows[0]["net_irrigation_need_mm"], 2.36)
        self.assertEqual(rows[1]["quality_status"], "WARN")
        self.assertIn("missing:et0_mm", rows[1]["quality_issues"])

    def test_normalizes_siar_and_checks_temperature_order(self):
        rows = normalize_siar_daily(
            [
                {
                    "Fecha": "2026-09-23T00:00:00",
                    "Estacion": "AL01",
                    "TempMedia": 21.1,
                    "TempMax": 26.3,
                    "TempMin": 17.3,
                    "HumedadMedia": 62.4,
                    "HumedadMax": 90,
                    "humedadMin": 40,
                    "VelViento": 0.6,
                    "VelVientoMax": 3.2,
                    "Radiacion": 21.7,
                    "Precipitacion": 0,
                    "EtPMon": 3.47,
                    "PePMon": 0,
                }
            ],
            ingested_at="2026-09-24T08:00:00+00:00",
            source_file="raw.json",
        )
        self.assertEqual(rows[0]["observed_date"], "2026-09-23")
        self.assertEqual(rows[0]["et0_pm_mm"], 3.47)
        self.assertEqual(rows[0]["quality_status"], "PASS")

    def test_normalizes_daily_code_and_horizon(self):
        payload = [
            {
                "id": "4013",
                "nombre": "Almería",
                "elaborado": "2026-09-24T07:19:08",
                "prediccion": {
                    "dia": [
                        {
                            "fecha": "2026-09-25T00:00:00",
                            "temperatura": {"minima": 20, "maxima": 29},
                            "humedadRelativa": {"minima": 40, "maxima": 90},
                            "probPrecipitacion": [{"periodo": "00-24", "value": 25}],
                            "estadoCielo": [{"periodo": "00-24", "value": "12", "descripcion": "Poco nuboso"}],
                            "viento": [{"periodo": "00-24", "direccion": "S", "velocidad": 15}],
                            "rachaMax": [{"periodo": "00-24", "value": 30}],
                        }
                    ]
                },
            }
        ]
        rows = normalize_aemet_daily(
            payload, ingested_at="2026-09-24T08:00:00+00:00", source_file="raw.json"
        )
        self.assertEqual(rows[0]["municipality_code"], "04013")
        self.assertEqual(rows[0]["horizon_days"], 1)
        self.assertEqual(rows[0]["precipitation_probability_max_pct"], 25)
        self.assertEqual(rows[0]["quality_status"], "PASS")

    def test_flattens_hourly_wind_gust_and_probabilities(self):
        payload = [
            {
                "id": "04013",
                "nombre": "Almería",
                "elaborado": "2026-09-24T07:00:00",
                "prediccion": {
                    "dia": [
                        {
                            "fecha": "2026-09-24T00:00:00",
                            "precipitacion": [{"periodo": "08", "value": "0"}],
                            "temperatura": [{"periodo": "08", "value": "22"}],
                            "humedadRelativa": [{"periodo": "08", "value": "47"}],
                            "probPrecipitacion": [{"periodo": "0814", "value": "10"}],
                            "probTormenta": [{"periodo": "0814", "value": "0"}],
                            "estadoCielo": [{"periodo": "08", "value": "12", "descripcion": "Poco nuboso"}],
                            "vientoAndRachaMax": [
                                {"periodo": "08", "direccion": ["N"], "velocidad": ["5"]},
                                {"periodo": "08", "value": "7"},
                            ],
                        }
                    ]
                },
            }
        ]
        rows = normalize_aemet_hourly(
            payload, ingested_at="2026-09-24T08:00:00+00:00", source_file="raw.json"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["precipitation_probability_pct"], 10)
        self.assertEqual(rows[0]["wind_direction"], "N")
        self.assertEqual(rows[0]["gust_kmh"], 7)
        self.assertEqual(rows[0]["quality_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
