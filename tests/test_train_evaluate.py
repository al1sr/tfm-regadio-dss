"""Pruebas del entrenamiento y la evaluacion temporal."""

import unittest

import numpy as np
import pandas as pd

from src.models.train_evaluate import (
    EXCLUDED_SAME_DAY_FEATURES,
    FEATURE_COLUMNS,
    TARGET,
    prepare_modeling_data,
    temporal_holdout,
    temporal_split,
    train_and_evaluate,
)


def sample_data(rows: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=rows, freq="D")
    target = 3.0 + np.sin(np.arange(rows) / 8) + np.arange(rows) * 0.01
    return pd.DataFrame(
        {
            "observed_date": dates,
            "crop_coefficient_kc": np.linspace(0.5, 0.9, rows),
            TARGET: target,
            "et0_mm": target / 0.7,
            "crop_evapotranspiration_etc_mm": target,
            "effective_precipitation_mm": 0.0,
        }
    )


class TrainEvaluateTests(unittest.TestCase):
    def test_features_use_only_previous_days(self):
        source = sample_data(40).drop(index=1).reset_index(drop=True)

        prepared = prepare_modeling_data(source)

        self.assertTrue(
            pd.isna(prepared.loc[1, "net_irrigation_need_mm_lag_1d"])
        )
        self.assertEqual(
            prepared.loc[2, "net_irrigation_need_mm_lag_3d"], source.loc[0, TARGET]
        )
        self.assertTrue(set(FEATURE_COLUMNS).issubset(prepared.columns))

    def test_reuses_features_prepared_in_section_4_2(self):
        source = sample_data(40)
        source["net_irrigation_need_mm_lag_1d"] = 99.0
        for lag in (3, 7):
            source[f"net_irrigation_need_mm_lag_{lag}d"] = 1.0
        for window in (3, 7, 14):
            source[f"net_irrigation_need_mm_sum_{window}d"] = 2.0

        prepared = prepare_modeling_data(source)

        self.assertTrue((prepared["net_irrigation_need_mm_lag_1d"] == 99.0).all())

    def test_temporal_split_preserves_order(self):
        split = temporal_split(prepare_modeling_data(sample_data()))

        self.assertLess(
            split.train["observed_date"].max(), split.validation["observed_date"].min()
        )
        self.assertLess(
            split.validation["observed_date"].max(), split.test["observed_date"].min()
        )
        self.assertEqual(len(split.train) + len(split.validation) + len(split.test), 80)

    def test_final_holdout_preserves_order(self):
        split = temporal_holdout(prepare_modeling_data(sample_data()))

        self.assertLess(
            split.development["observed_date"].max(), split.test["observed_date"].min()
        )
        self.assertEqual(len(split.development) + len(split.test), 80)

    def test_training_is_reproducible_and_excludes_same_day_formula(self):
        report_a, predictions_a, _ = train_and_evaluate(sample_data())
        report_b, predictions_b, _ = train_and_evaluate(sample_data())

        expected_models = {
            "persistence",
            "ridge",
            "random_forest",
            "knn",
            "svr",
            "xgboost",
        }
        self.assertIn(report_a["selected_model"], expected_models)
        self.assertEqual(set(report_a["test"]), expected_models)
        self.assertIn(report_a["selected_ml_candidate"], expected_models - {"persistence"})
        self.assertEqual(report_a["input_stage"], "processed_4_2")
        self.assertEqual(len(report_a["cross_validation"]["folds"]), 3)
        for model_name in report_a["test"]:
            for metric_name in report_a["test"][model_name]:
                self.assertAlmostEqual(
                    report_a["test"][model_name][metric_name],
                    report_b["test"][model_name][metric_name],
                )
        self.assertEqual(len(predictions_a), report_a["split"]["test_rows"])
        pd.testing.assert_frame_equal(predictions_a, predictions_b)
        self.assertTrue(set(EXCLUDED_SAME_DAY_FEATURES).isdisjoint(report_a["features"]))
        prediction_columns = [
            column
            for column in predictions_a
            if column.startswith("prediction_")
        ]
        self.assertEqual(len(prediction_columns), len(expected_models))
        self.assertTrue((predictions_a[prediction_columns] >= 0).all().all())
        self.assertEqual(report_a["persistence_horizon"], "one_step_ahead")
        self.assertIn("r2", report_a["test"]["persistence"])

    def test_rejects_small_datasets(self):
        with self.assertRaisesRegex(ValueError, "30 observaciones"):
            temporal_split(prepare_modeling_data(sample_data(20)))


if __name__ == "__main__":
    unittest.main()
