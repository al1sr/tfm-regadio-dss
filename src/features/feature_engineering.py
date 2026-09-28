"""Preparacion de variables para el modelo de necesidades de riego.

El modulo combina las tablas interim de SiAR y necesidades hidricas del cultivo
para generar una tabla analitica diaria. Cada fila representa una fecha,
estacion y cultivo, con variables meteorologicas depuradas, indicadores
temporales, retardos, acumulados y la necesidad neta de riego como objetivo.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_INTERIM_ROOT = Path("data/interim")
DEFAULT_PROCESSED_ROOT = Path("data/processed")


def _require_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{name} no contiene columnas requeridas: {', '.join(missing)}")


def _to_date(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        raise ValueError("Existen fechas no parseables en observed_date.")
    return parsed.dt.date.astype(str)


def _vapor_pressure_deficit_kpa(
    temperature_mean_c: pd.Series, humidity_mean_pct: pd.Series
) -> pd.Series:
    saturation = 0.6108 * np.exp(
        (17.27 * temperature_mean_c) / (temperature_mean_c + 237.3)
    )
    return saturation * (1 - humidity_mean_pct / 100)


def merge_weather_and_crop_needs(
    weather_daily: pd.DataFrame, crop_needs_daily: pd.DataFrame
) -> pd.DataFrame:
    """Une clima observado y necesidad neta por estacion y fecha."""
    _require_columns(
        weather_daily,
        {"station_code", "observed_date", "et0_pm_mm"},
        "weather_daily",
    )
    _require_columns(
        crop_needs_daily,
        {
            "station_code",
            "observed_date",
            "crop",
            "crop_coefficient_kc",
            "net_irrigation_need_mm",
        },
        "crop_needs_daily",
    )

    weather = weather_daily.copy()
    crop = crop_needs_daily.copy()
    weather["observed_date"] = _to_date(weather["observed_date"])
    crop["observed_date"] = _to_date(crop["observed_date"])

    merged = crop.merge(
        weather,
        on=["station_code", "observed_date"],
        how="left",
        suffixes=("_crop", "_weather"),
        validate="one_to_one",
    )

    merged["quality_status"] = np.where(
        (merged.get("quality_status_crop", "PASS") == "PASS")
        & (merged.get("quality_status_weather", "PASS") == "PASS"),
        "PASS",
        "WARN",
    )
    return merged.sort_values(["station_code", "crop", "observed_date"]).reset_index(
        drop=True
    )


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    dates = pd.to_datetime(out["observed_date"])
    out["year"] = dates.dt.year
    out["month"] = dates.dt.month
    out["week_of_year"] = dates.dt.isocalendar().week.astype(int)
    out["day_of_year"] = dates.dt.dayofyear
    out["day_of_year_sin"] = np.sin(2 * np.pi * out["day_of_year"] / 365.25)
    out["day_of_year_cos"] = np.cos(2 * np.pi * out["day_of_year"] / 365.25)
    return out


def add_agronomic_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if {"temperature_max_c", "temperature_min_c"}.issubset(out.columns):
        out["temperature_range_c"] = out["temperature_max_c"] - out["temperature_min_c"]

    if {"temperature_mean_c", "humidity_mean_pct"}.issubset(out.columns):
        out["vapor_pressure_deficit_kpa"] = _vapor_pressure_deficit_kpa(
            out["temperature_mean_c"], out["humidity_mean_pct"]
        )

    if {"et0_pm_mm", "crop_coefficient_kc"}.issubset(out.columns):
        out["etc_estimated_from_weather_mm"] = out["et0_pm_mm"] * out[
            "crop_coefficient_kc"
        ]

    if {"etc_estimated_from_weather_mm", "effective_precipitation_pm_mm"}.issubset(
        out.columns
    ):
        out["net_irrigation_need_estimated_mm"] = (
            out["etc_estimated_from_weather_mm"] - out["effective_precipitation_pm_mm"]
        ).clip(lower=0)

    return out


def add_lagged_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    group_cols = ["station_code", "crop"]
    lag_columns = [
        column
        for column in [
            "et0_pm_mm",
            "effective_precipitation_pm_mm",
            "precipitation_mm",
            "temperature_mean_c",
            "humidity_mean_pct",
            "solar_radiation_raw",
            "net_irrigation_need_mm",
        ]
        if column in out.columns
    ]

    for _, idx in out.groupby(group_cols, sort=False).groups.items():
        subset = out.loc[idx].sort_values("observed_date")
        for column in lag_columns:
            for lag in (1, 3, 7):
                out.loc[subset.index, f"{column}_lag_{lag}d"] = subset[column].shift(lag)
            for window in (3, 7, 14):
                shifted = subset[column].shift(1)
                if column in {
                    "precipitation_mm",
                    "effective_precipitation_pm_mm",
                    "net_irrigation_need_mm",
                }:
                    rolled = shifted.rolling(window, min_periods=1).sum()
                    suffix = "sum"
                else:
                    rolled = shifted.rolling(window, min_periods=1).mean()
                    suffix = "mean"
                out.loc[subset.index, f"{column}_{suffix}_{window}d"] = rolled

    return out


def build_modeling_dataset(
    weather_daily: pd.DataFrame, crop_needs_daily: pd.DataFrame
) -> pd.DataFrame:
    """Construye la tabla final de modelizacion del apartado 4.2."""
    dataset = merge_weather_and_crop_needs(weather_daily, crop_needs_daily)
    dataset = add_calendar_features(dataset)
    dataset = add_agronomic_features(dataset)
    dataset = add_lagged_features(dataset)
    dataset = dataset.rename(
        columns={"net_irrigation_need_mm": "target_net_irrigation_need_mm"}
    )
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interim-root", type=Path, default=DEFAULT_INTERIM_ROOT)
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    args = parser.parse_args()

    weather_path = args.interim_root / "siar_weather_daily.csv"
    crop_path = args.interim_root / "siar_crop_water_needs_daily.csv"
    output_path = args.processed_root / "modeling_dataset_daily.csv"

    weather = pd.read_csv(weather_path)
    crop = pd.read_csv(crop_path)
    dataset = build_modeling_dataset(weather, crop)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Tabla de modelizacion generada: {output_path}")
    print(f"Filas: {len(dataset)}")
    print(f"Columnas: {len(dataset.columns)}")


if __name__ == "__main__":
    main()

