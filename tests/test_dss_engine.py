"""Pruebas del motor de recomendación del DSS (capítulo 5)."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from src.dss.config import RecommendationRequest
from src.dss.data_access import load_crop_needs
from src.dss.engine import campaign_plan, recommend, weekly_table


def synthetic_history(days: int = 30) -> pd.DataFrame:
    dates = pd.date_range("2025-06-01", periods=days, freq="D")
    kc = np.where(np.arange(days) < 15, 0.7, 0.9)
    et0 = np.full(days, 5.0)
    pe = np.zeros(days)
    pe[10] = 6.0
    net = np.clip(et0 * kc - pe, 0, None)
    return pd.DataFrame(
        {
            "date": dates,
            "kc": kc,
            "et0_mm": et0,
            "etc_mm": et0 * kc,
            "pe_mm": pe,
            "net_need_mm": net,
            "record_status": "completo",
            "kc_imputed": False,
            "source_file": "sintetico.csv",
        }
    )


def run(history, **kwargs):
    forecast = kwargs.pop("forecast", None)
    request = RecommendationRequest(**kwargs)
    return recommend(request, history=history, metadata={}, forecast=forecast,
                     expected_errors={})


class LoadCropNeedsTests(unittest.TestCase):
    def test_missing_dates_are_kept_as_rows_without_need(self):
        content = (
            "Fecha;Kc;ET0 (mm);ETc (mm);Pe (mm);ETc - Pe (mm)\n"
            "01/05/2025;0,50;4,00;2,00;0,00;2,00\n"
            "03/05/2025;0,50;;;;\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "needs.csv"
            path.write_text(content, encoding="utf-8")
            data = load_crop_needs(path)

        self.assertEqual(len(data), 3)
        self.assertEqual(data.loc[1, "record_status"], "fecha_no_devuelta")
        self.assertTrue(data.loc[1, "kc_imputed"])
        self.assertTrue(pd.isna(data.loc[1, "net_need_mm"]))
        self.assertEqual(data.loc[2, "record_status"], "meteorologia_ausente")


class RecommendTests(unittest.TestCase):
    def setUp(self):
        self.history = synthetic_history()

    def test_planning_uses_only_previous_information(self):
        changed = self.history.copy()
        changed.loc[changed["date"] >= "2025-06-10", "et0_mm"] = 99.0
        base = run(self.history, issue_date=date(2025, 6, 10), horizon_days=3)
        altered = run(changed, issue_date=date(2025, 6, 10), horizon_days=3)
        pd.testing.assert_series_equal(base.daily["net_need_mm"], altered.daily["net_need_mm"])

    def test_recent_et0_times_calendar_kc(self):
        result = run(self.history, issue_date=date(2025, 6, 14), horizon_days=3)
        self.assertEqual(result.daily["method"].iat[0], "et0_reciente_kc")
        self.assertAlmostEqual(result.daily["net_need_mm"].iat[0], 5.0 * 0.7)
        self.assertAlmostEqual(result.daily["net_need_mm"].iat[2], 5.0 * 0.9)

    def test_gross_dose_and_volume(self):
        result = run(self.history, issue_date=date(2025, 6, 20), horizon_days=1,
                     efficiency=0.8, area_ha=2.0)
        row = result.daily.iloc[0]
        self.assertAlmostEqual(row["gross_dose_mm"], row["net_need_mm"] / 0.8, places=3)
        self.assertAlmostEqual(row["volume_m3"], row["gross_dose_mm"] * 10 * 2.0, places=2)

    def test_monitoring_mode_reproduces_reference_and_never_negative(self):
        result = run(self.history, issue_date=date(2025, 6, 1), horizon_days=7,
                     mode="seguimiento")
        reference = self.history["net_need_mm"].head(7).to_numpy()
        np.testing.assert_allclose(result.daily["net_need_mm"], reference, atol=1e-9)
        self.assertTrue((result.daily["net_need_mm"] >= 0).all())

    def test_allocation_limits_total_dose(self):
        result = run(self.history, issue_date=date(2025, 6, 20), horizon_days=7,
                     weekly_allocation_mm=10)
        self.assertAlmostEqual(result.summary["gross_dose_total_mm"], 10.0, places=2)
        self.assertLess(result.summary["allocation_factor"], 1)
        self.assertTrue(result.warnings)

    def test_rain_forecast_warns_without_discount(self):
        forecast = pd.DataFrame({"date": ["2025-06-21"], "precipitation_mm": [15.0]})
        base = run(self.history, issue_date=date(2025, 6, 20), horizon_days=2)
        rainy = run(self.history, issue_date=date(2025, 6, 20), horizon_days=2,
                    forecast=forecast)
        self.assertIn("aplazar", rainy.daily["warnings"].iat[1])
        self.assertAlmostEqual(base.daily["gross_dose_mm"].iat[1],
                               rainy.daily["gross_dose_mm"].iat[1])

    def test_forecast_et0_has_priority_and_flags_extrapolation(self):
        forecast = pd.DataFrame({"date": ["2025-06-20"], "et0_mm": [12.0]})
        result = run(self.history, issue_date=date(2025, 6, 20), horizon_days=1,
                     forecast=forecast)
        self.assertEqual(result.daily["method"].iat[0], "et0_prevista")
        self.assertIn("extrapolación", result.daily["warnings"].iat[0])

    def test_outside_cycle_and_without_history_returns_no_dose(self):
        late = run(self.history, issue_date=date(2025, 6, 30), horizon_days=3)
        self.assertEqual(late.daily["method"].tolist()[1:], ["sin_recomendacion"] * 2)
        first = run(self.history, issue_date=date(2025, 6, 1), horizon_days=1)
        self.assertTrue(pd.isna(first.daily["gross_dose_mm"].iat[0]))

    def test_stale_data_lowers_confidence(self):
        history = self.history.copy()
        history.loc[history["date"].between("2025-06-15", "2025-06-19"), ["et0_mm", "net_need_mm"]] = np.nan
        result = run(history, issue_date=date(2025, 6, 20), horizon_days=2)
        self.assertTrue(result.warnings)
        self.assertTrue((result.daily["confidence"] == "baja").all())

    def test_invalid_requests_are_rejected(self):
        for kwargs in ({"efficiency": 1.5}, {"horizon_days": 0}, {"horizon_days": 8},
                       {"mode": "otro"}, {"irrigation_system": "manta"}):
            with self.assertRaises(ValueError):
                run(self.history, issue_date=date(2025, 6, 20), **kwargs)

    def test_daily_rows_are_traceable(self):
        result = run(self.history, issue_date=date(2025, 6, 20), horizon_days=7)
        for column in ("method", "rules_applied", "explanation", "source_file",
                       "data_last_observed"):
            self.assertTrue(result.daily[column].notna().all(), column)

    def test_save_writes_csv_and_json(self):
        result = run(self.history, issue_date=date(2025, 6, 20), horizon_days=2)
        with tempfile.TemporaryDirectory() as folder:
            paths = result.save(Path(folder))
            self.assertTrue(paths["csv"].exists())
            self.assertIn('"summary"', paths["json"].read_text(encoding="utf-8"))

    def test_campaign_plan_and_weekly_totals_are_consistent(self):
        plan = campaign_plan(RecommendationRequest(issue_date=date(2025, 6, 2)),
                             self.history, {})
        weekly = weekly_table(plan)
        self.assertAlmostEqual(weekly["net_need_mm"].sum(), plan["net_need_mm"].sum())
        self.assertIn("reference_need_mm", plan.columns)


class PilotDataTests(unittest.TestCase):
    def test_pilot_file_reproduces_official_totals(self):
        path = Path("data/external/siar_necesidades_pimiento_AL01_2025.csv")
        if not path.exists():
            self.skipTest("CSV del piloto no disponible")
        data = load_crop_needs(path)
        self.assertEqual(len(data), 153)
        # SiAR publica el total como suma de ETc menos suma de Pe; la suma de las
        # necesidades diarias, limitadas a cero, es algo mayor.
        total = data["etc_mm"].sum() - data["pe_mm"].sum()
        self.assertAlmostEqual(total, 530.46, delta=0.02)
        self.assertAlmostEqual(data["net_need_mm"].sum(), 531.05, places=2)


if __name__ == "__main__":
    unittest.main()
