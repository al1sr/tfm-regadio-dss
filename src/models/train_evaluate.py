"""Entrena y evalúa modelos temporales para anticipar la referencia SiAR.

El flujo consume la tabla analítica generada en el apartado 4.2. Solo utiliza
variables conocidas antes del día objetivo. La evaluación reserva el tramo
final como prueba y selecciona el enfoque mediante validación temporal con
ventana expansiva sobre el periodo de desarrollo.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "tfm-regadio-dss-matplotlib")
)

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.neighbors import KNeighborsRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from xgboost import XGBRegressor


DEFAULT_INPUT = Path("data/processed/modeling_dataset_daily.csv")
DEFAULT_REPORT = Path("docs/data_samples/model_evaluation_4_3.json")
DEFAULT_PREDICTIONS = Path("docs/data_samples/model_predictions_4_3.csv")
DEFAULT_MODEL = Path("models/irrigation_reference_model.joblib")
DEFAULT_IMAGE_ROOT = Path("docs/images")

TARGET = "target_net_irrigation_need_mm"
TARGET_LAG_1D = "net_irrigation_need_mm_lag_1d"
FEATURE_COLUMNS = [
    "crop_coefficient_kc",
    "day_of_year_sin",
    "day_of_year_cos",
    TARGET_LAG_1D,
    "net_irrigation_need_mm_lag_3d",
    "net_irrigation_need_mm_lag_7d",
    "net_irrigation_need_mm_sum_3d",
    "net_irrigation_need_mm_sum_7d",
    "net_irrigation_need_mm_sum_14d",
]
EXCLUDED_SAME_DAY_FEATURES = [
    "et0_mm",
    "et0_pm_mm",
    "crop_evapotranspiration_etc_mm",
    "effective_precipitation_mm",
    "effective_precipitation_pm_mm",
    "etc_estimated_from_weather_mm",
    "net_irrigation_need_estimated_mm",
]
MODEL_LABELS = {
    "persistence": "Persistencia",
    "ridge": "Ridge",
    "random_forest": "Random Forest",
    "knn": "KNN",
    "svr": "SVR",
    "xgboost": "XGBoost",
}
MODEL_ORDER = tuple(MODEL_LABELS)
ML_MODEL_NAMES = tuple(name for name in MODEL_ORDER if name != "persistence")


@dataclass(frozen=True)
class TemporalHoldout:
    development: pd.DataFrame
    test: pd.DataFrame


@dataclass(frozen=True)
class TemporalSplit:
    """División simple conservada para compatibilidad y pruebas unitarias."""

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


class PersistenceRegressor(BaseEstimator, RegressorMixin):
    """Baseline que repite la última necesidad diaria disponible."""

    def fit(self, features: pd.DataFrame, target: pd.Series):
        self.fallback_ = float(pd.Series(target).median())
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if not hasattr(self, "fallback_"):
            raise ValueError("El baseline de persistencia no está ajustado.")
        values = pd.to_numeric(features[TARGET_LAG_1D], errors="coerce")
        return values.fillna(self.fallback_).clip(lower=0).to_numpy(dtype=float)


def load_modeling_dataset(path: Path) -> pd.DataFrame:
    """Carga la tabla procesada del apartado 4.2 y valida su contrato mínimo."""
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Ejecute antes: python -m src.analysis.build_eda_4_2"
        )
    source = pd.read_csv(path)
    required = {"observed_date", "crop_coefficient_kc", TARGET}
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"Faltan columnas de modelización: {', '.join(missing)}")
    return source


def prepare_modeling_data(source: pd.DataFrame) -> pd.DataFrame:
    """Valida o genera los predictores históricos seguros del apartado 4.2."""
    required = {"observed_date", "crop_coefficient_kc", TARGET}
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"Faltan columnas de modelización: {', '.join(missing)}")

    data = source.copy()
    data["observed_date"] = pd.to_datetime(data["observed_date"], errors="coerce")
    if data["observed_date"].isna().any():
        raise ValueError("Existen fechas no parseables en observed_date.")
    duplicate_key = [
        column for column in ("station_code", "crop", "observed_date") if column in data
    ]
    if data.duplicated(duplicate_key).any():
        raise ValueError("Existen claves duplicadas en el conjunto de modelización.")

    data = data.sort_values("observed_date").reset_index(drop=True)
    day_of_year = data["observed_date"].dt.dayofyear
    if "day_of_year_sin" not in data:
        data["day_of_year_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    if "day_of_year_cos" not in data:
        data["day_of_year_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)

    missing_features = [column for column in FEATURE_COLUMNS if column not in data]
    if missing_features:
        dates = pd.DatetimeIndex(data["observed_date"])
        calendar = pd.date_range(dates.min(), dates.max(), freq="D")
        daily_target = pd.Series(data[TARGET].to_numpy(), index=dates).reindex(calendar)
        for lag in (1, 3, 7):
            data[f"net_irrigation_need_mm_lag_{lag}d"] = (
                daily_target.shift(lag).reindex(dates).to_numpy()
            )
        for window in (3, 7, 14):
            data[f"net_irrigation_need_mm_sum_{window}d"] = (
                daily_target.shift(1)
                .rolling(window, min_periods=1)
                .sum()
                .reindex(dates)
                .to_numpy()
            )

    remaining = sorted(set(FEATURE_COLUMNS) - set(data.columns))
    if remaining:
        raise ValueError(f"No se pudieron generar predictores: {', '.join(remaining)}")
    return data.loc[data[TARGET].notna()].reset_index(drop=True)


def temporal_holdout(data: pd.DataFrame, test_fraction: float = 0.15) -> TemporalHoldout:
    """Reserva el tramo final como prueba sin mezclar pasado y futuro."""
    if len(data) < 30:
        raise ValueError("Se requieren al menos 30 observaciones con objetivo válido.")
    if not 0 < test_fraction < 0.5:
        raise ValueError("La fracción de prueba debe estar entre 0 y 0,5.")
    ordered = data.sort_values("observed_date").reset_index(drop=True)
    development_end = int(len(ordered) * (1 - test_fraction))
    return TemporalHoldout(
        development=ordered.iloc[:development_end].copy(),
        test=ordered.iloc[development_end:].copy(),
    )


def temporal_split(
    data: pd.DataFrame, train_fraction: float = 0.70, validation_fraction: float = 0.15
) -> TemporalSplit:
    """Compatibilidad: división temporal simple usada por pruebas anteriores."""
    if len(data) < 30:
        raise ValueError("Se requieren al menos 30 observaciones con objetivo válido.")
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("Las fracciones de entrenamiento y validación deben ser positivas.")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Debe reservarse una fracción temporal para prueba.")
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
    knn = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", KNeighborsRegressor(n_neighbors=7, weights="distance")),
        ]
    )
    svr = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", SVR(kernel="rbf", C=10.0, epsilon=0.1, gamma="scale")),
        ]
    )
    xgboost = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                XGBRegressor(
                    objective="reg:squarederror",
                    n_estimators=250,
                    learning_rate=0.03,
                    max_depth=2,
                    min_child_weight=3,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.05,
                    reg_lambda=1.5,
                    random_state=42,
                    n_jobs=1,
                ),
            ),
        ]
    )
    return {
        "persistence": PersistenceRegressor(),
        "ridge": ridge,
        "random_forest": forest,
        "knn": knn,
        "svr": svr,
        "xgboost": xgboost,
    }


def _nonnegative_prediction(model: RegressorMixin, features: pd.DataFrame) -> np.ndarray:
    """Aplica la restricción física de necesidad de riego no negativa."""
    return np.clip(np.asarray(model.predict(features), dtype=float), 0, None)


def regression_metrics(
    actual: pd.Series,
    predicted: np.ndarray,
    dates: pd.Series | None = None,
) -> dict[str, float]:
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    residual = predicted_values - actual_values
    if dates is None:
        blocks = np.arange(len(actual_values)) // 7
    else:
        parsed = pd.to_datetime(dates).reset_index(drop=True)
        blocks = ((parsed - parsed.min()).dt.days // 7).to_numpy()
    actual_weekly = pd.Series(actual_values).groupby(blocks).sum()
    predicted_weekly = pd.Series(predicted_values).groupby(blocks).sum()
    return {
        "mae_mm_day": float(mean_absolute_error(actual_values, predicted_values)),
        "rmse_mm_day": float(mean_squared_error(actual_values, predicted_values) ** 0.5),
        "r2": float(r2_score(actual_values, predicted_values)),
        "bias_mm_day": float(residual.mean()),
        "weekly_mae_mm": float(mean_absolute_error(actual_weekly, predicted_weekly)),
    }


def rolling_origin_validation(
    development: pd.DataFrame, n_splits: int = 3
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evalúa cada enfoque en varios cortes temporales con ventana expansiva."""
    splitter = TimeSeriesSplit(n_splits=n_splits)
    metrics_by_model: dict[str, list[dict[str, float]]] = {
        name: [] for name in _models()
    }
    fold_details: list[dict[str, Any]] = []
    for fold_number, (train_index, validation_index) in enumerate(
        splitter.split(development), start=1
    ):
        train = development.iloc[train_index]
        validation = development.iloc[validation_index]
        fold_metrics: dict[str, dict[str, float]] = {}
        for name, model in _models().items():
            model.fit(train[FEATURE_COLUMNS], train[TARGET])
            predicted = _nonnegative_prediction(model, validation[FEATURE_COLUMNS])
            metrics = regression_metrics(
                validation[TARGET], predicted, validation["observed_date"]
            )
            metrics_by_model[name].append(metrics)
            fold_metrics[name] = metrics
        fold_details.append(
            {
                "fold": fold_number,
                "train_rows": int(len(train)),
                "validation_rows": int(len(validation)),
                "train_start": train["observed_date"].min().date().isoformat(),
                "train_end": train["observed_date"].max().date().isoformat(),
                "validation_start": validation["observed_date"].min().date().isoformat(),
                "validation_end": validation["observed_date"].max().date().isoformat(),
                "metrics": fold_metrics,
            }
        )

    aggregate: dict[str, Any] = {}
    for name, observations in metrics_by_model.items():
        aggregate[name] = {}
        for metric in observations[0]:
            values = np.asarray([row[metric] for row in observations], dtype=float)
            aggregate[name][metric] = {
                "mean": float(values.mean()),
                "std": float(values.std(ddof=0)),
                "min": float(values.min()),
                "max": float(values.max()),
            }
    return aggregate, fold_details


def train_and_evaluate(data: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, Any]:
    """Selecciona por validación temporal y evalúa una vez sobre prueba."""
    prepared = prepare_modeling_data(data)
    holdout = temporal_holdout(prepared)
    cv_summary, cv_folds = rolling_origin_validation(holdout.development, n_splits=3)
    selected_name = min(
        cv_summary,
        key=lambda name: cv_summary[name]["mae_mm_day"]["mean"],
    )
    selected_ml_name = min(
        ML_MODEL_NAMES,
        key=lambda name: cv_summary[name]["mae_mm_day"]["mean"],
    )

    fitted: dict[str, RegressorMixin] = {}
    test_predictions: dict[str, np.ndarray] = {}
    for name, model in _models().items():
        model.fit(holdout.development[FEATURE_COLUMNS], holdout.development[TARGET])
        fitted[name] = model
        test_predictions[name] = _nonnegative_prediction(
            model, holdout.test[FEATURE_COLUMNS]
        )

    test_metrics = {
        name: regression_metrics(
            holdout.test[TARGET], predictions, holdout.test["observed_date"]
        )
        for name, predictions in test_predictions.items()
    }
    test_best_name = min(test_metrics, key=lambda name: test_metrics[name]["mae_mm_day"])

    prediction_table = holdout.test[["observed_date", TARGET]].copy()
    prediction_table["observed_date"] = prediction_table["observed_date"].dt.date.astype(str)
    for name, predictions in test_predictions.items():
        prediction_table[f"prediction_{name}_mm"] = predictions
        prediction_table[f"absolute_error_{name}_mm"] = np.abs(
            predictions - holdout.test[TARGET].to_numpy(dtype=float)
        )

    report: dict[str, Any] = {
        "objective": "Anticipar la referencia diaria de necesidad neta de SiAR",
        "input_stage": "processed_4_2",
        "target": TARGET,
        "data_start": prepared["observed_date"].min().date().isoformat(),
        "data_end": prepared["observed_date"].max().date().isoformat(),
        "valid_rows": int(len(prepared)),
        "random_seed": 42,
        "selection_method": "3-fold expanding-window temporal validation",
        "selection_metric": "cross_validation.mae_mm_day.mean",
        "selected_model": selected_name,
        "selected_ml_candidate": selected_ml_name,
        "test_best_model": test_best_name,
        "features": FEATURE_COLUMNS,
        "excluded_same_day_features": EXCLUDED_SAME_DAY_FEATURES,
        "prediction_constraint": "Predicciones recortadas a un mínimo de 0 mm/día",
        "model_definitions": {
            "persistence": (
                "Baseline de un día: la estimación de t es la necesidad observada "
                "en t-1; si falta, utiliza la mediana aprendida en entrenamiento."
            ),
            "ridge": "Regresión lineal regularizada con imputación y escalado.",
            "random_forest": "Conjunto conservador de 300 árboles de regresión.",
            "knn": "Regresión por siete vecinos próximos, distancia y variables escaladas.",
            "svr": "Support Vector Regression con kernel RBF, imputación y escalado.",
            "xgboost": "Gradient boosting de árboles con regularización y semilla fija.",
        },
        "persistence_horizon": "one_step_ahead",
        "split": {
            "development_rows": int(len(holdout.development)),
            "test_rows": int(len(holdout.test)),
            "development_start": holdout.development["observed_date"].min().date().isoformat(),
            "development_end": holdout.development["observed_date"].max().date().isoformat(),
            "test_start": holdout.test["observed_date"].min().date().isoformat(),
            "test_end": holdout.test["observed_date"].max().date().isoformat(),
        },
        "cross_validation": {
            "summary": cv_summary,
            "folds": cv_folds,
        },
        "test": test_metrics,
        "decision": (
            "Mantener la persistencia como referencia predictiva del piloto: ninguno "
            "de los cinco algoritmos de aprendizaje mejora su MAE medio de validación. "
            f"{MODEL_LABELS[selected_ml_name]} queda como mejor candidato de machine learning."
            if selected_name == "persistence"
            else f"Seleccionar {MODEL_LABELS[selected_name]} por su menor MAE medio de validación."
        ),
        "limitations": [
            "Un solo ciclo, cultivo y estación no permiten demostrar generalización.",
            "La etiqueta es una referencia calculada por SiAR, no riego real observado.",
            "No se puede afirmar ahorro de agua sin sensores, riego aplicado y respuesta del cultivo.",
            "La meteorología AEMET disponible no coincide temporalmente con el ciclo de entrenamiento.",
        ],
    }
    return report, prediction_table, fitted[selected_name]


def _apply_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.facecolor": "#F8FAFC",
            "figure.facecolor": "white",
            "grid.color": "#D9E2EC",
            "grid.alpha": 0.65,
        }
    )


def plot_predictions(predictions: pd.DataFrame, output: Path) -> None:
    dates = pd.to_datetime(predictions["observed_date"])
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.3), sharex=True, constrained_layout=True)
    axes[0].plot(dates, predictions[TARGET], color="#111827", lw=2.2, marker="o", ms=3.5, label="Referencia SiAR")
    palette = {
        "persistence": "#2563EB",
        "ridge": "#D97706",
        "random_forest": "#0F766E",
        "knn": "#7C3AED",
        "svr": "#DC2626",
        "xgboost": "#0891B2",
    }
    for name, color in palette.items():
        axes[0].plot(dates, predictions[f"prediction_{name}_mm"], color=color, lw=1.5, label=MODEL_LABELS[name])
    axes[0].set_ylabel("Necesidad neta (mm/día)")
    axes[0].set_title("Predicciones en el tramo de prueba")
    axes[0].legend(ncol=4, frameon=False, loc="upper center", fontsize=8)
    axes[0].grid(axis="y")
    for name, color in palette.items():
        residual = predictions[f"prediction_{name}_mm"] - predictions[TARGET]
        axes[1].plot(dates, residual, color=color, lw=1.4, label=MODEL_LABELS[name])
    axes[1].axhline(0, color="#111827", lw=1, ls="--")
    axes[1].set_ylabel("Error (mm/día)")
    axes[1].set_title("Error con signo: predicción menos referencia")
    axes[1].grid(axis="y")
    axes[1].xaxis.set_major_locator(mdates.DayLocator(interval=3))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.suptitle("Evaluación temporal del piloto de pimiento", fontsize=13, fontweight="bold")
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_validation(report: dict[str, Any], output: Path) -> None:
    model_names = list(MODEL_ORDER)
    folds = report["cross_validation"]["folds"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8), constrained_layout=True)
    palette = {
        "persistence": "#2563EB",
        "ridge": "#D97706",
        "random_forest": "#0F766E",
        "knn": "#7C3AED",
        "svr": "#DC2626",
        "xgboost": "#0891B2",
    }
    for name in model_names:
        values = [fold["metrics"][name]["mae_mm_day"] for fold in folds]
        axes[0].plot(range(1, len(values) + 1), values, marker="o", lw=1.8, color=palette[name], label=MODEL_LABELS[name])
    axes[0].set_xticks(range(1, len(folds) + 1))
    axes[0].set_xlabel("Corte temporal")
    axes[0].set_ylabel("MAE (mm/día)")
    axes[0].set_title("Validación con ventana expansiva")
    axes[0].grid(axis="y")
    axes[0].legend(frameon=False, fontsize=8, ncol=2)
    positions = np.arange(len(model_names))
    width = 0.36
    cv_means = [report["cross_validation"]["summary"][name]["mae_mm_day"]["mean"] for name in model_names]
    cv_std = [report["cross_validation"]["summary"][name]["mae_mm_day"]["std"] for name in model_names]
    test_mae = [report["test"][name]["mae_mm_day"] for name in model_names]
    axes[1].bar(positions - width / 2, cv_means, width, yerr=cv_std, capsize=4, color="#64748B", label="Validación: media ± desviación")
    axes[1].bar(positions + width / 2, test_mae, width, color="#2563EB", label="Prueba final")
    axes[1].set_xticks(positions, [MODEL_LABELS[name] for name in model_names], rotation=28, ha="right")
    axes[1].set_ylabel("MAE (mm/día)")
    axes[1].set_title("Error medio de validación y prueba")
    axes[1].grid(axis="y")
    axes[1].legend(frameon=False, fontsize=8)
    fig.suptitle("Estabilidad temporal de los modelos", fontsize=13, fontweight="bold")
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Entrena y evalúa modelos temporales del apartado 4.3."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    source = load_modeling_dataset(args.input)
    report, predictions, model = train_and_evaluate(source)

    for path in (args.report, args.predictions, args.model):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.image_root.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    predictions.to_csv(args.predictions, index=False, encoding="utf-8-sig")
    joblib.dump(
        {"model": model, "features": FEATURE_COLUMNS, "target": TARGET}, args.model
    )
    _apply_plot_style()
    plot_predictions(predictions, args.image_root / "model_predictions_4_3.png")
    plot_validation(report, args.image_root / "model_validation_4_3.png")

    selected = report["selected_model"]
    metrics = report["test"][selected]
    print(f"Enfoque seleccionado por validación temporal: {selected}")
    print(f"MAE prueba: {metrics['mae_mm_day']:.3f} mm/día")
    print(f"RMSE prueba: {metrics['rmse_mm_day']:.3f} mm/día")
    print(f"Informe: {args.report}")


if __name__ == "__main__":
    main()
