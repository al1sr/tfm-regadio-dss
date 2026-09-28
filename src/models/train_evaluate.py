"""Entrena y evalua modelos temporales para anticipar la referencia SiAR.

El objetivo es la necesidad neta diaria publicada por SiAR. Los predictores
usan exclusivamente calendario, Kc conocido y valores historicos desplazados;
se excluyen ET0, ETc y precipitacion efectiva del mismo dia para evitar fuga
algebraica de informacion.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import RegressorMixin
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


DEFAULT_INPUT = Path("data/external/siar_necesidades_pimiento_AL01_2025.csv")
DEFAULT_REPORT = Path("results/reports/model_evaluation_4_3.json")
DEFAULT_PREDICTIONS = Path("results/reports/model_predictions_4_3.csv")
DEFAULT_MODEL = Path("models/irrigation_reference_model.joblib")

TARGET = "target_net_irrigation_need_mm"
FEATURE_COLUMNS = [
    "crop_coefficient_kc",
    "day_of_year_sin",
    "day_of_year_cos",
    "target_lag_1d",
    "target_lag_3d",
    "target_lag_7d",
    "target_mean_3d",
    "target_mean_7d",
    "target_mean_14d",
]


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def load_siar_reference(path: Path) -> pd.DataFrame:
    """Carga el CSV oficial de necesidades, conservando los nulos."""
    source = pd.read_csv(path, sep=";", decimal=",")
    required = {
        "Fecha",
        "Kc",
        "ET0 (mm)",
        "ETc (mm)",
        "Pe (mm)",
        "ETc - Pe (mm)",
    }
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"Faltan columnas SiAR: {', '.join(missing)}")

    return source.rename(
        columns={
            "Fecha": "observed_date",
            "Kc": "crop_coefficient_kc",
            "ET0 (mm)": "et0_mm",
            "ETc (mm)": "crop_evapotranspiration_etc_mm",
            "Pe (mm)": "effective_precipitation_mm",
            "ETc - Pe (mm)": TARGET,
        }
    )


def prepare_modeling_data(source: pd.DataFrame) -> pd.DataFrame:
    """Crea predictores conocidos antes del dia objetivo."""
    required = {"observed_date", "crop_coefficient_kc", TARGET}
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"Faltan columnas de modelizacion: {', '.join(missing)}")

    data = source.copy()
    data["observed_date"] = pd.to_datetime(
        data["observed_date"], dayfirst=True, errors="coerce"
    )
    if data["observed_date"].isna().any():
        raise ValueError("Existen fechas no parseables en observed_date.")
    if data["observed_date"].duplicated().any():
        raise ValueError("Existen fechas duplicadas en el conjunto de modelizacion.")

    data = data.sort_values("observed_date").reset_index(drop=True)
    day_of_year = data["observed_date"].dt.dayofyear
    data["day_of_year_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    data["day_of_year_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)

    dates = pd.DatetimeIndex(data["observed_date"])
    calendar = pd.date_range(dates.min(), dates.max(), freq="D")
    daily_target = pd.Series(data[TARGET].to_numpy(), index=dates).reindex(calendar)
    for lag in (1, 3, 7):
        data[f"target_lag_{lag}d"] = daily_target.shift(lag).reindex(dates).to_numpy()
    for window in (3, 7, 14):
        data[f"target_mean_{window}d"] = (
            daily_target.shift(1)
            .rolling(window, min_periods=1)
            .mean()
            .reindex(dates)
            .to_numpy()
        )

    return data.loc[data[TARGET].notna()].reset_index(drop=True)


def temporal_split(
    data: pd.DataFrame, train_fraction: float = 0.70, validation_fraction: float = 0.15
) -> TemporalSplit:
    """Divide por fecha sin mezclar observaciones futuras y pasadas."""
    if len(data) < 30:
        raise ValueError("Se requieren al menos 30 observaciones con objetivo valido.")
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("Las fracciones de entrenamiento y validacion deben ser positivas.")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Debe reservarse una fraccion temporal para prueba.")

    ordered = data.sort_values("observed_date").reset_index(drop=True)
    train_end = int(len(ordered) * train_fraction)
    validation_end = int(len(ordered) * (train_fraction + validation_fraction))
    return TemporalSplit(
        train=ordered.iloc[:train_end].copy(),
        validation=ordered.iloc[train_end:validation_end].copy(),
        test=ordered.iloc[validation_end:].copy(),
    )


def _models() -> dict[str, RegressorMixin]:
    ridge = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=1.0)),
        ]
    )
    forest = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=300,
                    max_depth=5,
                    min_samples_leaf=4,
                    random_state=42,
                    n_jobs=1,
                ),
            ),
        ]
    )
    return {"ridge": ridge, "random_forest": forest}


def regression_metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    residual = predicted_values - actual_values
    blocks = np.arange(len(actual_values)) // 7
    actual_weekly = pd.Series(actual_values).groupby(blocks).sum()
    predicted_weekly = pd.Series(predicted_values).groupby(blocks).sum()
    return {
        "mae_mm_day": float(mean_absolute_error(actual_values, predicted_values)),
        "rmse_mm_day": float(mean_squared_error(actual_values, predicted_values) ** 0.5),
        "bias_mm_day": float(residual.mean()),
        "weekly_mae_mm": float(mean_absolute_error(actual_weekly, predicted_weekly)),
    }


def _persistence_prediction(frame: pd.DataFrame, fallback: float) -> np.ndarray:
    return frame["target_lag_1d"].fillna(fallback).to_numpy(dtype=float)


def train_and_evaluate(data: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, Any]:
    """Selecciona con validacion y evalua una unica vez sobre prueba."""
    prepared = prepare_modeling_data(data)
    split = temporal_split(prepared)
    train_median = float(split.train[TARGET].median())

    validation_metrics: dict[str, dict[str, float]] = {
        "persistence": regression_metrics(
            split.validation[TARGET],
            _persistence_prediction(split.validation, train_median),
        )
    }
    fitted: dict[str, RegressorMixin] = {}
    for name, model in _models().items():
        model.fit(split.train[FEATURE_COLUMNS], split.train[TARGET])
        fitted[name] = model
        validation_metrics[name] = regression_metrics(
            split.validation[TARGET], model.predict(split.validation[FEATURE_COLUMNS])
        )

    selected_name = min(
        fitted,
        key=lambda name: validation_metrics[name]["mae_mm_day"],
    )
    train_validation = pd.concat([split.train, split.validation], ignore_index=True)
    selected_model = _models()[selected_name]
    selected_model.fit(train_validation[FEATURE_COLUMNS], train_validation[TARGET])

    test_predictions: dict[str, np.ndarray] = {
        "persistence": _persistence_prediction(split.test, train_median)
    }
    for name, model in _models().items():
        model.fit(train_validation[FEATURE_COLUMNS], train_validation[TARGET])
        test_predictions[name] = model.predict(split.test[FEATURE_COLUMNS])

    test_metrics = {
        name: regression_metrics(split.test[TARGET], predictions)
        for name, predictions in test_predictions.items()
    }
    prediction_table = split.test[["observed_date", TARGET]].copy()
    for name, predictions in test_predictions.items():
        prediction_table[f"prediction_{name}_mm"] = predictions

    report: dict[str, Any] = {
        "objective": "Anticipar la referencia diaria de necesidad neta de SiAR",
        "target": TARGET,
        "data_start": prepared["observed_date"].min().date().isoformat(),
        "data_end": prepared["observed_date"].max().date().isoformat(),
        "random_seed": 42,
        "selected_model": selected_name,
        "selection_metric": "validation.mae_mm_day",
        "features": FEATURE_COLUMNS,
        "excluded_same_day_features": [
            "et0_mm",
            "crop_evapotranspiration_etc_mm",
            "effective_precipitation_mm",
        ],
        "split": {
            "train_rows": len(split.train),
            "validation_rows": len(split.validation),
            "test_rows": len(split.test),
            "train_end": split.train["observed_date"].max().date().isoformat(),
            "validation_end": split.validation["observed_date"].max().date().isoformat(),
            "test_start": split.test["observed_date"].min().date().isoformat(),
            "test_end": split.test["observed_date"].max().date().isoformat(),
        },
        "validation": validation_metrics,
        "test": test_metrics,
        "limitations": [
            "Un solo ciclo, cultivo y estacion no permiten demostrar generalizacion.",
            "La etiqueta es una referencia calculada por SiAR, no riego real observado.",
            "No se puede afirmar ahorro de agua sin sensores, riego aplicado y respuesta del cultivo.",
        ],
    }
    return report, prediction_table, selected_model


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Entrena y evalua modelos temporales del apartado 4.3."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    source = load_siar_reference(args.input)
    report, predictions, model = train_and_evaluate(source)

    for path in (args.report, args.predictions, args.model):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    predictions.to_csv(args.predictions, index=False, encoding="utf-8-sig")
    joblib.dump(
        {"model": model, "features": FEATURE_COLUMNS, "target": TARGET}, args.model
    )

    selected = report["selected_model"]
    metrics = report["test"][selected]
    print(f"Modelo seleccionado: {selected}")
    print(f"MAE prueba: {metrics['mae_mm_day']:.3f} mm/dia")
    print(f"RMSE prueba: {metrics['rmse_mm_day']:.3f} mm/dia")
    print(f"Informe: {args.report}")


if __name__ == "__main__":
    main()
