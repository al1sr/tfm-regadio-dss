"""Lectura de la referencia agronómica y de la predicción meteorológica.

El motor trabaja con un calendario diario completo. Las fechas que la fuente no
devuelve se conservan como filas sin dato y con una marca explícita, de modo que
una ausencia nunca se confunde con una necesidad nula.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.dss.config import CropCase


CROP_NEEDS_COLUMNS = {
    "Fecha": "date",
    "Kc": "kc",
    "ET0 (mm)": "et0_mm",
    "ETc (mm)": "etc_mm",
    "Pe (mm)": "pe_mm",
    "ETc - Pe (mm)": "net_need_mm",
}

FORECAST_COLUMNS = {"date", "et0_mm", "precipitation_mm", "precipitation_probability_pct"}


def load_crop_needs(path: Path) -> pd.DataFrame:
    """Carga el CSV oficial de SiAR y devuelve un calendario diario completo."""

    if not Path(path).exists():
        raise FileNotFoundError(f"No se encuentra la referencia agronómica: {path}")

    raw = pd.read_csv(path, sep=";", decimal=",", encoding="utf-8-sig")
    missing = set(CROP_NEEDS_COLUMNS).difference(raw.columns)
    if missing:
        raise ValueError(f"Faltan columnas en la referencia SiAR: {sorted(missing)}")

    data = raw.rename(columns=CROP_NEEDS_COLUMNS)[list(CROP_NEEDS_COLUMNS.values())]
    data["date"] = pd.to_datetime(data["date"], dayfirst=True, errors="raise")
    for column in ("kc", "et0_mm", "etc_mm", "pe_mm", "net_need_mm"):
        data[column] = pd.to_numeric(data[column], errors="coerce")

    if data["date"].duplicated().any():
        raise ValueError("La referencia SiAR contiene fechas duplicadas.")

    calendar = pd.date_range(data["date"].min(), data["date"].max(), freq="D")
    data = data.set_index("date").reindex(calendar)
    data.index.name = "date"
    data["record_status"] = "completo"
    data.loc[data["kc"].isna(), "record_status"] = "fecha_no_devuelta"
    data.loc[
        data["kc"].notna() & data["et0_mm"].isna(), "record_status"
    ] = "meteorologia_ausente"
    # El Kc procede del calendario del cultivo y se conoce de antemano. Si falta
    # una fecha, se toma el último valor publicado y se deja constancia.
    data["kc_imputed"] = data["kc"].isna()
    data["kc"] = data["kc"].ffill()
    data["source_file"] = Path(path).as_posix()
    return data.reset_index()


def load_metadata(path: Path) -> dict[str, Any]:
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_case(case: CropCase) -> tuple[pd.DataFrame, dict[str, Any]]:
    return load_crop_needs(case.source_file), load_metadata(case.metadata_file)


def load_forecast(path: Path | None) -> pd.DataFrame | None:
    """Carga una predicción diaria opcional.

    Se espera un CSV con ``date`` y, al menos, una de las columnas ``et0_mm``,
    ``precipitation_mm`` o ``precipitation_probability_pct``. Puede proceder de
    la predicción municipal de AEMET normalizada en ``data/interim`` o del
    producto de ET0 prevista de SiAR.
    """

    if path is None:
        return None
    forecast = pd.read_csv(path)
    if "date" not in forecast.columns:
        for alias in ("valid_date", "forecast_date", "fecha"):
            if alias in forecast.columns:
                forecast = forecast.rename(columns={alias: "date"})
                break
    if "date" not in forecast.columns:
        raise ValueError("La predicción debe incluir una columna de fecha.")
    if not FORECAST_COLUMNS.difference({"date"}).intersection(forecast.columns):
        raise ValueError("La predicción no contiene ninguna variable utilizable.")
    forecast["date"] = pd.to_datetime(forecast["date"]).dt.normalize()
    return normalise_forecast(forecast)


def normalise_forecast(forecast: pd.DataFrame | None) -> pd.DataFrame | None:
    if forecast is None:
        return None
    result = forecast.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    for column in FORECAST_COLUMNS.difference({"date"}):
        if column not in result.columns:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result[sorted(FORECAST_COLUMNS)].drop_duplicates("date", keep="last")
