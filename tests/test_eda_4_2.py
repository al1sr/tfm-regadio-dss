"""Pruebas del analisis exploratorio reproducible del apartado 4.2."""

import unittest

import pandas as pd

from src.analysis.build_eda_4_2 import (
    build_feature_catalog,
    build_summary,
    calendar_diagnostics,
)


class EdaSection42Tests(unittest.TestCase):
    def setUp(self):
        self.dataset = pd.DataFrame(
            [
                {
                    "station_code": "AL01",
                    "crop": "Pimiento",
                    "observed_date": "2025-05-01",
                    "quality_status": "PASS",
                    "temperature_mean_c": 20.0,
                    "temperature_min_c": 15.0,
                    "temperature_max_c": 25.0,
                    "humidity_mean_pct": 60.0,
                    "wind_speed_mean_ms": 2.0,
                    "solar_radiation_raw": 20.0,
                    "precipitation_mm": 0.0,
                    "et0_pm_mm": 4.0,
                    "crop_coefficient_kc": 0.5,
                    "target_net_irrigation_need_mm": 2.0,
                    "crop_evapotranspiration_etc_mm": 2.0,
                    "effective_precipitation_mm": 0.0,
                    "net_irrigation_need_mm_lag_1d": float("nan"),
                },
                {
                    "station_code": "AL01",
                    "crop": "Pimiento",
                    "observed_date": "2025-05-03",
                    "quality_status": "WARN",
                    "temperature_mean_c": 22.0,
                    "temperature_min_c": 16.0,
                    "temperature_max_c": 28.0,
                    "humidity_mean_pct": 55.0,
                    "wind_speed_mean_ms": 3.0,
                    "solar_radiation_raw": 22.0,
                    "precipitation_mm": 0.0,
                    "et0_pm_mm": 5.0,
                    "crop_coefficient_kc": 0.5,
                    "target_net_irrigation_need_mm": 2.5,
                    "crop_evapotranspiration_etc_mm": 2.5,
                    "effective_precipitation_mm": 0.0,
                    "net_irrigation_need_mm_lag_1d": float("nan"),
                },
            ]
        )

    def test_calendar_reports_real_gap(self):
        result = calendar_diagnostics(self.dataset)
        self.assertEqual(result["missing_dates"], ["2025-05-02"])
        self.assertEqual(result["expected_calendar_days"], 3)

    def test_summary_counts_quality_and_target(self):
        result = build_summary(self.dataset)
        self.assertEqual(result["dataset"]["rows"], 2)
        self.assertEqual(result["dataset"]["quality_status_counts"]["WARN"], 1)
        self.assertEqual(result["target"]["total"], 4.5)

    def test_catalog_marks_direct_leakage_and_safe_lag(self):
        catalog = build_feature_catalog(self.dataset).set_index("variable")
        self.assertTrue(bool(catalog.loc["crop_evapotranspiration_etc_mm", "leakage_risk"]))
        self.assertFalse(bool(catalog.loc["net_irrigation_need_mm_lag_1d", "leakage_risk"]))
        self.assertEqual(catalog.loc["target_net_irrigation_need_mm", "role"], "objetivo")


if __name__ == "__main__":
    unittest.main()
