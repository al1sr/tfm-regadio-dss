"""Genera las evidencias reproducibles del apartado 4.2 de la memoria.

El script parte de las tablas normalizadas del apartado 4.1, construye la
tabla diaria de modelizacion y guarda un resumen estadistico, un catalogo de
variables, una muestra verificable y cuatro figuras. Los datos completos se
mantienen fuera de Git; solo se versionan evidencias pequenas y trazables.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "tfm-regadio-dss-matplotlib")
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.features.feature_engineering import build_modeling_dataset


DEFAULT_INTERIM_ROOT = Path("data/interim")
DEFAULT_PROCESSED_ROOT = Path("data/processed")
DEFAULT_EVIDENCE_ROOT = Path("docs/data_samples")
DEFAULT_IMAGE_ROOT = Path("docs/images")

TARGET = "target_net_irrigation_need_mm"
KEY_COLUMNS = ["station_code", "crop", "observed_date"]
EDA_VARIABLES = [
    "temperature_mean_c",
    "temperature_max_c",
    "temperature_min_c",
    "humidity_mean_pct",
    "wind_speed_mean_ms",
    "solar_radiation_raw",
    "precipitation_mm",
    "et0_pm_mm",
    "crop_coefficient_kc",
    "crop_evapotranspiration_etc_mm",
    "effective_precipitation_mm",
    TARGET,
    "temperature_range_c",
    "vapor_pressure_deficit_kpa",
]

METADATA_PREFIXES = ("source", "ingested_at")
QUALITY_PREFIXES = ("quality_status", "quality_issues")
IDENTIFIERS = {
    "station_code",
    "station_name",
    "region",
    "crop",
    "observed_date",
}
DIRECT_LEAKAGE = {
    "crop_evapotranspiration_etc_mm",
    "effective_precipitation_mm",
    "etc_estimated_from_weather_mm",
    "net_irrigation_need_estimated_mm",
}


def calendar_diagnostics(dataset: pd.DataFrame) -> dict[str, Any]:
    """Resume cobertura y huecos del calendario para cada serie piloto."""
    dates = pd.to_datetime(dataset["observed_date"], errors="raise")
    start = dates.min()
    end = dates.max()
    expected = pd.date_range(start, end, freq="D")
    present = pd.DatetimeIndex(dates.drop_duplicates().sort_values())
    missing = expected.difference(present)
    return {
        "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(),
        "expected_calendar_days": int(len(expected)),
        "observed_unique_days": int(len(present)),
        "missing_calendar_days": int(len(missing)),
        "missing_dates": [date.date().isoformat() for date in missing],
    }


def numeric_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    """Crea una tabla descriptiva compacta de las variables principales."""
    variables = [column for column in EDA_VARIABLES if column in dataset.columns]
    rows: list[dict[str, Any]] = []
    for column in variables:
        series = pd.to_numeric(dataset[column], errors="coerce")
        clean = series.dropna()
        rows.append(
            {
                "variable": column,
                "count": int(clean.count()),
                "missing": int(series.isna().sum()),
                "missing_pct": round(float(series.isna().mean() * 100), 2),
                "mean": round(float(clean.mean()), 4) if not clean.empty else None,
                "std": round(float(clean.std()), 4) if len(clean) > 1 else None,
                "min": round(float(clean.min()), 4) if not clean.empty else None,
                "p25": round(float(clean.quantile(0.25)), 4) if not clean.empty else None,
                "median": round(float(clean.median()), 4) if not clean.empty else None,
                "p75": round(float(clean.quantile(0.75)), 4) if not clean.empty else None,
                "max": round(float(clean.max()), 4) if not clean.empty else None,
            }
        )
    return pd.DataFrame(rows)


def _feature_metadata(column: str) -> tuple[str, str, bool, str]:
    """Clasifica una columna por papel, disponibilidad y riesgo de fuga."""
    if column == TARGET:
        return "objetivo", "solo tras observar/calcular el dia", False, "variable a predecir"
    if column in IDENTIFIERS:
        return "identificador", "conocida", False, "clave o segmentacion; no se escala"
    if column.startswith(METADATA_PREFIXES) or column.startswith(QUALITY_PREFIXES):
        return "trazabilidad_calidad", "conocida", False, "control; no predictor"
    if column in DIRECT_LEAKAGE:
        return (
            "diagnostico",
            "contemporanea al objetivo",
            True,
            "excluir del entrenamiento predictivo por fuga directa",
        )
    if column.startswith("net_irrigation_need_mm_lag_") or column.startswith(
        "net_irrigation_need_mm_sum_"
    ):
        return (
            "predictora_historica",
            "disponible antes de la prediccion",
            False,
            "usar solo con desplazamiento temporal",
        )
    if "_lag_" in column or "_mean_" in column or "_sum_" in column:
        return (
            "predictora_historica",
            "disponible antes de la prediccion",
            False,
            "retardo o ventana calculada con shift(1)",
        )
    if column in {"crop_coefficient_kc", "year", "month", "week_of_year", "day_of_year", "day_of_year_sin", "day_of_year_cos"}:
        return "predictora_planificada", "conocida de antemano", False, "candidata"
    if column in {"et0_mm", "effective_precipitation_pm_mm"}:
        return (
            "predictora_condicionada",
            "observada; requiere equivalente pronosticado",
            False,
            "no usar como valor futuro real en produccion",
        )
    return (
        "predictora_meteorologica",
        "observada; requiere pronostico para horizonte futuro",
        False,
        "candidata para nowcast o con equivalente AEMET",
    )


def build_feature_catalog(dataset: pd.DataFrame) -> pd.DataFrame:
    """Documenta todas las columnas de la tabla analitica."""
    rows = []
    for column in dataset.columns:
        role, availability, leakage, recommendation = _feature_metadata(column)
        rows.append(
            {
                "variable": column,
                "dtype": str(dataset[column].dtype),
                "role": role,
                "availability_at_prediction": availability,
                "leakage_risk": leakage,
                "modeling_recommendation": recommendation,
                "missing_count": int(dataset[column].isna().sum()),
                "missing_pct": round(float(dataset[column].isna().mean() * 100), 2),
            }
        )
    return pd.DataFrame(rows)


def build_summary(dataset: pd.DataFrame) -> dict[str, Any]:
    """Calcula indicadores de cobertura, calidad y objetivo."""
    calendar = calendar_diagnostics(dataset)
    target = pd.to_numeric(dataset[TARGET], errors="coerce")
    duplicate_keys = int(dataset.duplicated(KEY_COLUMNS).sum())
    quality_counts = {
        str(key): int(value)
        for key, value in dataset["quality_status"].value_counts(dropna=False).items()
    }
    numeric = dataset.select_dtypes(include=[np.number])
    out_of_range = {
        "humidity_outside_0_100": int(
            ((dataset["humidity_mean_pct"] < 0) | (dataset["humidity_mean_pct"] > 100)).sum()
        ),
        "negative_et0": int((dataset["et0_pm_mm"] < 0).sum()),
        "negative_precipitation": int((dataset["precipitation_mm"] < 0).sum()),
        "negative_target": int((target < 0).sum()),
        "temperature_order_violations": int(
            (
                (dataset["temperature_min_c"] > dataset["temperature_mean_c"])
                | (dataset["temperature_mean_c"] > dataset["temperature_max_c"])
            ).sum()
        ),
    }
    correlations = (
        numeric[[c for c in [TARGET, "et0_pm_mm", "crop_coefficient_kc", "temperature_mean_c", "humidity_mean_pct", "solar_radiation_raw", "precipitation_mm"] if c in numeric.columns]]
        .corr()[TARGET]
        .drop(TARGET)
        .sort_values(ascending=False)
    )
    return {
        "scope": {
            "station_codes": sorted(dataset["station_code"].dropna().astype(str).unique().tolist()),
            "crops": sorted(dataset["crop"].dropna().astype(str).unique().tolist()),
            **calendar,
        },
        "dataset": {
            "rows": int(len(dataset)),
            "columns": int(len(dataset.columns)),
            "duplicate_keys": duplicate_keys,
            "complete_target_rows": int(target.notna().sum()),
            "target_missing_rows": int(target.isna().sum()),
            "quality_status_counts": quality_counts,
            "columns_with_missing_values": int((dataset.isna().sum() > 0).sum()),
        },
        "target": {
            "unit": "mm/dia",
            "mean": round(float(target.mean()), 4),
            "median": round(float(target.median()), 4),
            "minimum": round(float(target.min()), 4),
            "maximum": round(float(target.max()), 4),
            "standard_deviation": round(float(target.std()), 4),
            "total": round(float(target.sum()), 4),
            "zero_days": int((target == 0).sum()),
        },
        "agronomic_checks": out_of_range,
        "pearson_correlations_with_target": {
            key: round(float(value), 4) for key, value in correlations.items()
        },
        "aemet_alignment": {
            "status": "not_joined_for_training",
            "reason": (
                "La muestra AEMET disponible corresponde a una prediccion emitida en 2026, "
                "mientras que el piloto SiAR corresponde a 2025. Se conserva como prueba de "
                "integracion operativa, no como predictor historico del entrenamiento."
            ),
        },
    }


def _apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.facecolor": "#F8FAFC",
            "grid.color": "#D9E2EC",
            "grid.alpha": 0.65,
        }
    )


def plot_time_series(dataset: pd.DataFrame, output: Path) -> None:
    frame = dataset.copy()
    frame["observed_date"] = pd.to_datetime(frame["observed_date"])
    frame = frame.sort_values("observed_date")
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True, constrained_layout=True)
    axes[0].plot(frame["observed_date"], frame["et0_pm_mm"], color="#1D4ED8", lw=1.4, label="ET0")
    axes[0].plot(frame["observed_date"], frame["crop_evapotranspiration_etc_mm"], color="#0F766E", lw=1.4, label="ETc")
    axes[0].plot(frame["observed_date"], frame[TARGET], color="#D97706", lw=1.7, label="Necesidad neta")
    axes[0].set_ylabel("Milímetros por día")
    axes[0].set_title("Demanda evaporativa y necesidad neta de riego")
    axes[0].legend(ncol=3, frameon=False, loc="upper right")
    axes[0].grid(axis="y")
    axes[1].step(frame["observed_date"], frame["crop_coefficient_kc"], where="mid", color="#7C3AED", lw=1.8, label="Kc")
    axes[1].bar(frame["observed_date"], frame["effective_precipitation_mm"], color="#38BDF8", width=1.0, alpha=0.7, label="Precipitación efectiva")
    axes[1].set_ylabel("Kc / mm")
    axes[1].set_title("Evolución del cultivo y aportes efectivos de lluvia")
    axes[1].legend(ncol=2, frameon=False, loc="upper right")
    axes[1].grid(axis="y")
    axes[1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.suptitle("Piloto pimiento · estación AL01 La Mojonera · mayo-septiembre 2025", fontsize=13, fontweight="bold")
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_distributions(dataset: pd.DataFrame, output: Path) -> None:
    variables = [
        ("temperature_mean_c", "Temperatura media (°C)", "#DC2626"),
        ("humidity_mean_pct", "Humedad media (%)", "#2563EB"),
        ("et0_pm_mm", "ET0 (mm/día)", "#0F766E"),
        (TARGET, "Necesidad neta (mm/día)", "#D97706"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 6.3), constrained_layout=True)
    for axis, (column, label, color) in zip(axes.flat, variables):
        clean = pd.to_numeric(dataset[column], errors="coerce").dropna()
        axis.hist(clean, bins=16, color=color, alpha=0.82, edgecolor="white")
        axis.axvline(clean.median(), color="#111827", ls="--", lw=1.2, label=f"Mediana: {clean.median():.2f}")
        axis.set_title(label)
        axis.set_ylabel("Número de días")
        axis.grid(axis="y")
        axis.legend(frameon=False, fontsize=8)
    fig.suptitle("Distribución de variables principales del piloto", fontsize=13, fontweight="bold")
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_correlations(dataset: pd.DataFrame, output: Path) -> None:
    variables = [
        "temperature_mean_c",
        "humidity_mean_pct",
        "wind_speed_mean_ms",
        "solar_radiation_raw",
        "precipitation_mm",
        "et0_pm_mm",
        "crop_coefficient_kc",
        TARGET,
    ]
    labels = ["Temp.", "Humedad", "Viento", "Radiación", "Precip.", "ET0", "Kc", "Necesidad neta"]
    corr = dataset[variables].corr()
    fig, axis = plt.subplots(figsize=(8.2, 6.8), constrained_layout=True)
    image = axis.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    axis.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    axis.set_yticks(range(len(labels)), labels)
    for row in range(len(labels)):
        for col in range(len(labels)):
            value = corr.iloc[row, col]
            axis.text(col, row, f"{value:.2f}", ha="center", va="center", fontsize=7.5, color="white" if abs(value) > 0.55 else "#111827")
    axis.set_title("Correlaciones de Pearson entre variables seleccionadas", fontsize=13, fontweight="bold", pad=12)
    colorbar = fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    colorbar.set_label("Correlación")
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_quality(dataset: pd.DataFrame, output: Path) -> None:
    dates = pd.to_datetime(dataset["observed_date"])
    calendar = pd.date_range(dates.min(), dates.max(), freq="D")
    observed = pd.Series(1, index=pd.DatetimeIndex(dates)).reindex(calendar, fill_value=0)
    missing = dataset.isna().sum().sort_values(ascending=False)
    missing = missing[(missing > 0) & ~missing.index.str.startswith(("quality_issues",))].head(12)
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.3), constrained_layout=True)
    axes[0].barh(missing.index[::-1], missing.values[::-1], color="#64748B")
    axes[0].set_xlabel("Registros ausentes")
    axes[0].set_title("Variables con valores ausentes en la tabla analítica")
    axes[0].grid(axis="x")
    axes[1].scatter(calendar[observed.eq(1)], np.ones(int(observed.eq(1).sum())), s=14, color="#0F766E", label="Fecha disponible")
    axes[1].scatter(calendar[observed.eq(0)], np.zeros(int(observed.eq(0).sum())), s=45, marker="x", color="#DC2626", label="Fecha ausente")
    axes[1].set_yticks([0, 1], ["Ausente", "Disponible"])
    axes[1].set_ylim(-0.35, 1.35)
    axes[1].set_title("Continuidad del calendario diario")
    axes[1].legend(frameon=False, loc="lower right")
    axes[1].grid(axis="x")
    axes[1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.suptitle("Controles de completitud y continuidad", fontsize=13, fontweight="bold")
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)


def write_evidence(
    dataset: pd.DataFrame,
    evidence_root: Path,
    image_root: Path,
) -> dict[str, Any]:
    evidence_root.mkdir(parents=True, exist_ok=True)
    image_root.mkdir(parents=True, exist_ok=True)
    summary = build_summary(dataset)
    (evidence_root / "eda_summary_4_2.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    numeric_summary(dataset).to_csv(
        evidence_root / "eda_variable_summary_4_2.csv", index=False, encoding="utf-8-sig"
    )
    build_feature_catalog(dataset).to_csv(
        evidence_root / "feature_catalog_4_2.csv", index=False, encoding="utf-8-sig"
    )
    sample_columns = [
        "station_code",
        "crop",
        "observed_date",
        "quality_status",
        "temperature_mean_c",
        "humidity_mean_pct",
        "solar_radiation_raw",
        "precipitation_mm",
        "et0_pm_mm",
        "crop_coefficient_kc",
        "crop_evapotranspiration_etc_mm",
        "effective_precipitation_mm",
        TARGET,
        "vapor_pressure_deficit_kpa",
        "et0_pm_mm_lag_1d",
        "precipitation_mm_sum_7d",
        "net_irrigation_need_mm_lag_1d",
    ]
    sample_indexes = sorted(set([*range(min(5, len(dataset))), *range(max(0, len(dataset) - 5), len(dataset)), *dataset.index[dataset["quality_status"].ne("PASS")].tolist()]))
    dataset.loc[sample_indexes, sample_columns].to_csv(
        evidence_root / "modeling_dataset_sample_4_2.csv", index=False, encoding="utf-8-sig"
    )
    _apply_style()
    plot_time_series(dataset, image_root / "eda_series_4_2.png")
    plot_distributions(dataset, image_root / "eda_distributions_4_2.png")
    plot_correlations(dataset, image_root / "eda_correlations_4_2.png")
    plot_quality(dataset, image_root / "eda_quality_4_2.png")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interim-root", type=Path, default=DEFAULT_INTERIM_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT)
    args = parser.parse_args()

    weather = pd.read_csv(args.interim_root / "siar_weather_daily.csv")
    crop = pd.read_csv(args.interim_root / "siar_crop_water_needs_daily.csv")
    dataset = build_modeling_dataset(weather, crop)
    args.processed_root.mkdir(parents=True, exist_ok=True)
    output = args.processed_root / "modeling_dataset_daily.csv"
    dataset.to_csv(output, index=False, encoding="utf-8-sig")
    summary = write_evidence(dataset, args.evidence_root, args.image_root)
    print(f"Tabla de modelizacion: {output} ({len(dataset)} filas, {len(dataset.columns)} columnas)")
    print(f"Fechas ausentes: {summary['scope']['missing_dates']}")
    print(f"Filas WARN: {summary['dataset']['quality_status_counts'].get('WARN', 0)}")


if __name__ == "__main__":
    main()
