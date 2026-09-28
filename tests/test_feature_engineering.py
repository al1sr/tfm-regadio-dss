"""Pruebas de preparacion de variables para modelizacion."""

import unittest

import pandas as pd

from src.features.feature_engineering import build_modeling_dataset


class FeatureEngineeringTests(unittest.TestCase):
    def test_builds_calendar_agronomic_and_lag_features(self):
        weather = pd.DataFrame(
            [
                {
                    "station_code": "AL01",
                    "observed_date": "2025-05-01",
                    "temperature_mean_c": 19.0,
                    "temperature_max_c": 25.0,
                    "temperature_min_c": 14.0,
                    "humidity_mean_pct": 70.0,
                    "solar_radiation_raw": 20.0,
                    "precipitation_mm": 0.0,
                    "et0_pm_mm": 4.0,
                    "effective_precipitation_pm_mm": 0.0,
                    "quality_status": "PASS",
                },
                {
                    "station_code": "AL01",
                    "observed_date": "2025-05-02",
                    "temperature_mean_c": 20.0,
                    "temperature_max_c": 27.0,
                    "temperature_min_c": 15.0,
                    "humidity_mean_pct": 65.0,
                    "solar_radiation_raw": 21.0,
                    "precipitation_mm": 1.0,
                    "et0_pm_mm": 5.0,
                    "effective_precipitation_pm_mm": 0.5,
                    "quality_status": "PASS",
                },
            ]
        )
        crop = pd.DataFrame(
            [
                {
                    "station_code": "AL01",
                    "crop": "Pimiento",
                    "observed_date": "2025-05-01",
                    "crop_coefficient_kc": 0.5,
                    "net_irrigation_need_mm": 2.0,
                    "quality_status": "PASS",
                },
                {
                    "station_code": "AL01",
                    "crop": "Pimiento",
                    "observed_date": "2025-05-02",
                    "crop_coefficient_kc": 0.5,
                    "net_irrigation_need_mm": 2.0,
                    "quality_status": "PASS",
                },
            ]
        )

        dataset = build_modeling_dataset(weather, crop)

        self.assertEqual(len(dataset), 2)
        self.assertIn("day_of_year_sin", dataset.columns)
        self.assertIn("temperature_range_c", dataset.columns)
        self.assertIn("vapor_pressure_deficit_kpa", dataset.columns)
        self.assertIn("et0_pm_mm_lag_1d", dataset.columns)
        self.assertEqual(dataset.loc[0, "temperature_range_c"], 11.0)
        self.assertTrue(pd.isna(dataset.loc[0, "et0_pm_mm_lag_1d"]))
        self.assertEqual(dataset.loc[1, "et0_pm_mm_lag_1d"], 4.0)
        self.assertEqual(dataset.loc[1, "target_net_irrigation_need_mm"], 2.0)

    def test_marks_warn_when_weather_quality_warns(self):
        weather = pd.DataFrame(
            [
                {
                    "station_code": "AL01",
                    "observed_date": "2025-05-01",
                    "et0_pm_mm": 4.0,
                    "quality_status": "WARN",
                }
            ]
        )
        crop = pd.DataFrame(
            [
                {
                    "station_code": "AL01",
                    "crop": "Pimiento",
                    "observed_date": "2025-05-01",
                    "crop_coefficient_kc": 0.5,
                    "net_irrigation_need_mm": 2.0,
                    "quality_status": "PASS",
                }
            ]
        )

        dataset = build_modeling_dataset(weather, crop)

        self.assertEqual(dataset.loc[0, "quality_status"], "WARN")


if __name__ == "__main__":
    unittest.main()

