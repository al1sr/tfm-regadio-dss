"""Normalización de las extracciones raw del piloto.

Convierte los JSON trazables de SiAR y AEMET en tablas planas CSV listas para
análisis. La capa raw no se modifica y cada fila conserva procedencia, fecha de
ingestión y controles de calidad.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


DEFAULT_RAW_ROOT = Path("data/raw")
DEFAULT_INTERIM_ROOT = Path("data/interim")
DEFAULT_EXTERNAL_ROOT = Path("data/external")


@dataclass(frozen=True)
class TableResult:
    dataset: str
    path: Path
    record_count: int
    warning_count: int


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _iso_date(value: str) -> str:
    return datetime.fromisoformat(value).date().isoformat()


def _quality(issues: Iterable[str]) -> tuple[str, str]:
    clean = sorted(set(issue for issue in issues if issue))
    return ("PASS" if not clean else "WARN", "; ".join(clean))


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _load_latest(root: Path, pattern: str) -> tuple[dict[str, Any], Path]:
    candidates = list(root.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"No se encontró ningún archivo raw para {pattern}.")
    path = max(candidates, key=lambda candidate: candidate.stat().st_mtime)
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or "data" not in document:
        raise ValueError(f"El archivo {path} no contiene un sobre raw válido.")
    return document, path


def normalize_siar_daily(
    records: list[dict[str, Any]], *, ingested_at: str, source_file: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        temp_mean = _number(record.get("TempMedia"))
        temp_max = _number(record.get("TempMax"))
        temp_min = _number(record.get("TempMin"))
        humidity_mean = _number(record.get("HumedadMedia"))
        humidity_max = _number(record.get("HumedadMax"))
        humidity_min = _number(record.get("humedadMin"))
        wind_mean = _number(record.get("VelViento"))
        wind_max = _number(record.get("VelVientoMax"))
        radiation = _number(record.get("Radiacion"))
        precipitation = _number(record.get("Precipitacion"))
        et0 = _number(record.get("EtPMon"))
        effective_precipitation = _number(record.get("PePMon"))

        issues: list[str] = []
        required = {
            "temperature_mean_c": temp_mean,
            "temperature_max_c": temp_max,
            "temperature_min_c": temp_min,
            "humidity_mean_pct": humidity_mean,
            "wind_speed_mean_ms": wind_mean,
            "solar_radiation": radiation,
            "precipitation_mm": precipitation,
            "et0_pm_mm": et0,
            "effective_precipitation_pm_mm": effective_precipitation,
        }
        issues.extend(f"missing:{name}" for name, value in required.items() if value is None)
        if None not in (temp_min, temp_mean, temp_max) and not (
            temp_min <= temp_mean <= temp_max
        ):
            issues.append("invalid:temperature_order")
        for name, value in (
            ("humidity_mean_pct", humidity_mean),
            ("humidity_max_pct", humidity_max),
            ("humidity_min_pct", humidity_min),
        ):
            if value is not None and not 0 <= value <= 100:
                issues.append(f"invalid:{name}")
        for name, value in (
            ("wind_speed_mean_ms", wind_mean),
            ("wind_speed_max_ms", wind_max),
            ("solar_radiation", radiation),
            ("precipitation_mm", precipitation),
            ("et0_pm_mm", et0),
            ("effective_precipitation_pm_mm", effective_precipitation),
        ):
            if value is not None and value < 0:
                issues.append(f"invalid:{name}")
        status, detail = _quality(issues)
        rows.append(
            {
                "source": "SiAR",
                "station_code": _text(record.get("Estacion")),
                "observed_date": _iso_date(record["Fecha"]),
                "temperature_mean_c": temp_mean,
                "temperature_max_c": temp_max,
                "temperature_min_c": temp_min,
                "humidity_mean_pct": humidity_mean,
                "humidity_max_pct": humidity_max,
                "humidity_min_pct": humidity_min,
                "wind_speed_mean_ms": wind_mean,
                "wind_direction_raw": _number(record.get("DirViento")),
                "wind_speed_max_ms": wind_max,
                "solar_radiation_raw": radiation,
                "precipitation_mm": precipitation,
                "soil_temperature_1_c": _number(record.get("TempSuelo1")),
                "soil_temperature_2_c": _number(record.get("TempSuelo2")),
                "et0_pm_mm": et0,
                "effective_precipitation_pm_mm": effective_precipitation,
                "quality_status": status,
                "quality_issues": detail,
                "ingested_at": ingested_at,
                "source_file": source_file,
            }
        )
    return rows


def normalize_siar_crop_needs(
    records: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
    source_file: str,
) -> list[dict[str, Any]]:
    """Normaliza el CSV descargado del cálculo de necesidades netas."""
    rows: list[dict[str, Any]] = []
    for record in records:
        kc = _number(record.get("Kc"))
        et0 = _number(record.get("ET0 (mm)"))
        etc = _number(record.get("ETc (mm)"))
        effective_precipitation = _number(record.get("Pe (mm)"))
        net_need = _number(record.get("ETc - Pe (mm)"))
        date_text = _text(record.get("Fecha"))
        issues: list[str] = []
        if not date_text:
            issues.append("missing:observed_date")
            observed_date = None
        else:
            try:
                observed_date = datetime.strptime(date_text, "%d/%m/%Y").date().isoformat()
            except ValueError:
                observed_date = None
                issues.append("invalid:observed_date")
        if kc is None:
            issues.append("missing:crop_coefficient_kc")
        for name, value in (
            ("et0_mm", et0),
            ("crop_evapotranspiration_etc_mm", etc),
            ("effective_precipitation_mm", effective_precipitation),
            ("net_irrigation_need_mm", net_need),
        ):
            if value is None:
                issues.append(f"missing:{name}")
            elif value < 0:
                issues.append(f"invalid:{name}")
        if kc is not None and not 0 <= kc <= 2:
            issues.append("invalid:crop_coefficient_kc")
        if None not in (kc, et0, etc) and abs(etc - kc * et0) > 0.02:
            issues.append("inconsistent:etc_vs_kc_et0")
        if None not in (etc, effective_precipitation, net_need):
            expected = max(etc - effective_precipitation, 0)
            if abs(net_need - expected) > 0.02:
                issues.append("inconsistent:net_need")
        status, detail = _quality(issues)
        rows.append(
            {
                "source": "SiAR necesidades netas",
                "station_code": _text(metadata.get("station_code")),
                "station_name": _text(metadata.get("station_name")),
                "region": _text(metadata.get("region")),
                "crop": _text(metadata.get("crop")),
                "observed_date": observed_date,
                "crop_coefficient_kc": kc,
                "et0_mm": et0,
                "crop_evapotranspiration_etc_mm": etc,
                "effective_precipitation_mm": effective_precipitation,
                "net_irrigation_need_mm": net_need,
                "quality_status": status,
                "quality_issues": detail,
                "ingested_at": _text(metadata.get("retrieved_at")),
                "source_file": source_file,
            }
        )
    return rows


def _period_item(items: list[dict[str, Any]], period: str) -> dict[str, Any] | None:
    return next((item for item in items if str(item.get("periodo")) == period), None)


def _period_value(items: list[dict[str, Any]], period: str) -> Any:
    item = _period_item(items, period)
    return item.get("value") if item else None


def normalize_aemet_daily(
    payload: list[dict[str, Any]], *, ingested_at: str, source_file: str
) -> list[dict[str, Any]]:
    if not payload:
        return []
    root = payload[0]
    issued = datetime.fromisoformat(root["elaborado"])
    code_raw = str(root.get("id", ""))
    code = code_raw.removeprefix("id").zfill(5)
    rows: list[dict[str, Any]] = []
    for day in root.get("prediccion", {}).get("dia", []):
        valid_date = datetime.fromisoformat(day["fecha"]).date()
        temperature = day.get("temperatura") or {}
        humidity = day.get("humedadRelativa") or {}
        precipitation_items = day.get("probPrecipitacion") or []
        probability = _number(_period_value(precipitation_items, "00-24"))
        if probability is None:
            values = [_number(item.get("value")) for item in precipitation_items]
            probability = max((value for value in values if value is not None), default=None)
        sky = _period_item(day.get("estadoCielo") or [], "00-24") or {}
        wind = _period_item(day.get("viento") or [], "00-24") or {}
        gust = _number(_period_value(day.get("rachaMax") or [], "00-24"))
        temp_min = _number(temperature.get("minima"))
        temp_max = _number(temperature.get("maxima"))
        humidity_min = _number(humidity.get("minima"))
        humidity_max = _number(humidity.get("maxima"))
        issues: list[str] = []
        for name, value in (
            ("temperature_min_c", temp_min),
            ("temperature_max_c", temp_max),
            ("humidity_min_pct", humidity_min),
            ("humidity_max_pct", humidity_max),
            ("precipitation_probability_max_pct", probability),
        ):
            if value is None:
                issues.append(f"missing:{name}")
        if None not in (temp_min, temp_max) and temp_min > temp_max:
            issues.append("invalid:temperature_order")
        for name, value in (
            ("humidity_min_pct", humidity_min),
            ("humidity_max_pct", humidity_max),
            ("precipitation_probability_max_pct", probability),
        ):
            if value is not None and not 0 <= value <= 100:
                issues.append(f"invalid:{name}")
        status, detail = _quality(issues)
        rows.append(
            {
                "source": "AEMET",
                "municipality_code": code,
                "municipality_code_raw": code_raw,
                "municipality_name": _text(root.get("nombre")),
                "issued_at": issued.isoformat(),
                "valid_date": valid_date.isoformat(),
                "horizon_days": (valid_date - issued.date()).days,
                "temperature_min_c": temp_min,
                "temperature_max_c": temp_max,
                "humidity_min_pct": humidity_min,
                "humidity_max_pct": humidity_max,
                "precipitation_probability_max_pct": probability,
                "sky_code_24h": _text(sky.get("value")),
                "sky_description_24h": _text(sky.get("descripcion")),
                "wind_direction_24h": _text(wind.get("direccion")),
                "wind_speed_24h_kmh": _number(wind.get("velocidad")),
                "gust_24h_kmh": gust,
                "uv_max": _number(day.get("uvMax")),
                "quality_status": status,
                "quality_issues": detail,
                "ingested_at": ingested_at,
                "source_file": source_file,
            }
        )
    return rows


def _hourly_map(items: list[dict[str, Any]], key: str = "value") -> dict[int, Any]:
    result: dict[int, Any] = {}
    for item in items:
        period = str(item.get("periodo", ""))
        if period.isdigit() and len(period) <= 2:
            hour = int(period)
            if 0 <= hour <= 23:
                result[hour] = item.get(key)
    return result


def _interval_contains(period: str, hour: int) -> bool:
    if not period.isdigit() or len(period) != 4:
        return False
    start, end = int(period[:2]), int(period[2:])
    return start <= hour < end if start < end else hour >= start or hour < end


def _interval_value(items: list[dict[str, Any]], hour: int) -> Any:
    item = next(
        (item for item in items if _interval_contains(str(item.get("periodo", "")), hour)),
        None,
    )
    return item.get("value") if item else None


def normalize_aemet_hourly(
    payload: list[dict[str, Any]], *, ingested_at: str, source_file: str
) -> list[dict[str, Any]]:
    if not payload:
        return []
    root = payload[0]
    issued = datetime.fromisoformat(root["elaborado"])
    code_raw = str(root.get("id", ""))
    code = code_raw.removeprefix("id").zfill(5)
    rows: list[dict[str, Any]] = []
    for day in root.get("prediccion", {}).get("dia", []):
        base_date = datetime.fromisoformat(day["fecha"]).date()
        precipitation = _hourly_map(day.get("precipitacion") or [])
        temperature = _hourly_map(day.get("temperatura") or [])
        humidity = _hourly_map(day.get("humedadRelativa") or [])
        sky_items = day.get("estadoCielo") or []
        sky = _hourly_map(sky_items)
        sky_description = _hourly_map(sky_items, "descripcion")
        wind: dict[int, tuple[Any, Any]] = {}
        gust: dict[int, Any] = {}
        for item in day.get("vientoAndRachaMax") or []:
            period = str(item.get("periodo", ""))
            if not period.isdigit() or not 0 <= int(period) <= 23:
                continue
            hour = int(period)
            if "direccion" in item or "velocidad" in item:
                directions = item.get("direccion") or []
                speeds = item.get("velocidad") or []
                wind[hour] = (
                    directions[0] if isinstance(directions, list) and directions else None,
                    speeds[0] if isinstance(speeds, list) and speeds else None,
                )
            elif "value" in item:
                gust[hour] = item.get("value")
        hours = sorted(set(precipitation) | set(temperature) | set(humidity) | set(sky) | set(wind) | set(gust))
        for hour in hours:
            valid = datetime.combine(base_date, datetime.min.time()).replace(hour=hour)
            temp = _number(temperature.get(hour))
            hum = _number(humidity.get(hour))
            precip = _number(precipitation.get(hour))
            probability = _number(_interval_value(day.get("probPrecipitacion") or [], hour))
            storm_probability = _number(_interval_value(day.get("probTormenta") or [], hour))
            direction, speed = wind.get(hour, (None, None))
            issues: list[str] = []
            for name, value in (
                ("temperature_c", temp),
                ("humidity_pct", hum),
                ("precipitation_mm", precip),
                ("precipitation_probability_pct", probability),
            ):
                if value is None:
                    issues.append(f"missing:{name}")
            if hum is not None and not 0 <= hum <= 100:
                issues.append("invalid:humidity_pct")
            if probability is not None and not 0 <= probability <= 100:
                issues.append("invalid:precipitation_probability_pct")
            if precip is not None and precip < 0:
                issues.append("invalid:precipitation_mm")
            horizon_hours = (valid - issued).total_seconds() / 3600
            status, detail = _quality(issues)
            rows.append(
                {
                    "source": "AEMET",
                    "municipality_code": code,
                    "municipality_code_raw": code_raw,
                    "municipality_name": _text(root.get("nombre")),
                    "issued_at": issued.isoformat(),
                    "valid_time_local": valid.isoformat(),
                    "horizon_hours": round(horizon_hours, 3),
                    "is_future_at_issue": horizon_hours >= 0,
                    "temperature_c": temp,
                    "humidity_pct": hum,
                    "precipitation_mm": precip,
                    "precipitation_probability_pct": probability,
                    "storm_probability_pct": storm_probability,
                    "sky_code": _text(sky.get(hour)),
                    "sky_description": _text(sky_description.get(hour)),
                    "wind_direction": _text(direction),
                    "wind_speed_kmh": _number(speed),
                    "gust_kmh": _number(gust.get(hour)),
                    "quality_status": status,
                    "quality_issues": detail,
                    "ingested_at": ingested_at,
                    "source_file": source_file,
                }
            )
    return rows


SIAR_FIELDS = [
    "source", "station_code", "observed_date", "temperature_mean_c",
    "temperature_max_c", "temperature_min_c", "humidity_mean_pct",
    "humidity_max_pct", "humidity_min_pct", "wind_speed_mean_ms",
    "wind_direction_raw", "wind_speed_max_ms", "solar_radiation_raw",
    "precipitation_mm", "soil_temperature_1_c", "soil_temperature_2_c",
    "et0_pm_mm", "effective_precipitation_pm_mm", "quality_status",
    "quality_issues", "ingested_at", "source_file",
]

AEMET_DAILY_FIELDS = [
    "source", "municipality_code", "municipality_code_raw", "municipality_name",
    "issued_at", "valid_date", "horizon_days", "temperature_min_c",
    "temperature_max_c", "humidity_min_pct", "humidity_max_pct",
    "precipitation_probability_max_pct", "sky_code_24h",
    "sky_description_24h", "wind_direction_24h", "wind_speed_24h_kmh",
    "gust_24h_kmh", "uv_max", "quality_status", "quality_issues",
    "ingested_at", "source_file",
]

AEMET_HOURLY_FIELDS = [
    "source", "municipality_code", "municipality_code_raw", "municipality_name",
    "issued_at", "valid_time_local", "horizon_hours", "is_future_at_issue",
    "temperature_c", "humidity_pct", "precipitation_mm",
    "precipitation_probability_pct", "storm_probability_pct", "sky_code",
    "sky_description", "wind_direction", "wind_speed_kmh", "gust_kmh",
    "quality_status", "quality_issues", "ingested_at", "source_file",
]

CROP_NEEDS_FIELDS = [
    "source", "station_code", "station_name", "region", "crop",
    "observed_date", "crop_coefficient_kc", "et0_mm",
    "crop_evapotranspiration_etc_mm", "effective_precipitation_mm",
    "net_irrigation_need_mm", "quality_status", "quality_issues",
    "ingested_at", "source_file",
]


def _duplicates(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> int:
    values = [tuple(row.get(key) for key in keys) for row in rows]
    return len(values) - len(set(values))


def _calendar_gaps(rows: list[dict[str, Any]]) -> list[str] | None:
    """Devuelve fechas ausentes entre el mínimo y máximo de una tabla diaria."""
    values = {
        row.get("observed_date") or row.get("valid_date")
        for row in rows
        if row.get("observed_date") or row.get("valid_date")
    }
    parsed = sorted(date.fromisoformat(value) for value in values)
    if not parsed:
        return None
    expected: set[date] = set()
    current = parsed[0]
    while current <= parsed[-1]:
        expected.add(current)
        current += timedelta(days=1)
    return [value.isoformat() for value in sorted(expected - set(parsed))]


def transform_interim(
    raw_root: Path = DEFAULT_RAW_ROOT,
    interim_root: Path = DEFAULT_INTERIM_ROOT,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
) -> list[TableResult]:
    siar_doc, siar_file = _load_latest(raw_root, "siar/weather/daily/**/*.json")
    daily_doc, daily_file = _load_latest(raw_root, "aemet/forecast/daily/**/*.json")
    hourly_doc, hourly_file = _load_latest(raw_root, "aemet/forecast/hourly/**/*.json")

    siar_rows = normalize_siar_daily(
        siar_doc["data"],
        ingested_at=siar_doc["ingested_at"],
        source_file=str(siar_file),
    )
    daily_rows = normalize_aemet_daily(
        daily_doc["data"],
        ingested_at=daily_doc["ingested_at"],
        source_file=str(daily_file),
    )
    hourly_rows = normalize_aemet_hourly(
        hourly_doc["data"],
        ingested_at=hourly_doc["ingested_at"],
        source_file=str(hourly_file),
    )

    crop_needs_files = list(external_root.glob("siar_necesidades_*.csv"))
    if not crop_needs_files:
        raise FileNotFoundError(
            "No se encontró el CSV de necesidades hídricas en data/external."
        )
    crop_needs_file = max(
        crop_needs_files, key=lambda candidate: candidate.stat().st_mtime
    )
    metadata_file = crop_needs_file.with_suffix(".metadata.json")
    if not metadata_file.exists():
        raise FileNotFoundError(
            f"Falta el fichero de metadatos asociado: {metadata_file}."
        )
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    with crop_needs_file.open("r", encoding="utf-8-sig", newline="") as stream:
        crop_needs_records = list(csv.DictReader(stream, delimiter=";"))
    crop_needs_rows = normalize_siar_crop_needs(
        crop_needs_records,
        metadata=metadata,
        source_file=str(crop_needs_file),
    )

    tables = [
        ("siar_weather_daily", siar_rows, SIAR_FIELDS, ("station_code", "observed_date")),
        ("siar_crop_water_needs_daily", crop_needs_rows, CROP_NEEDS_FIELDS, ("station_code", "crop", "observed_date")),
        ("aemet_forecast_daily", daily_rows, AEMET_DAILY_FIELDS, ("municipality_code", "issued_at", "valid_date")),
        ("aemet_forecast_hourly", hourly_rows, AEMET_HOURLY_FIELDS, ("municipality_code", "issued_at", "valid_time_local")),
    ]
    outputs: list[TableResult] = []
    quality_rows: list[dict[str, Any]] = []
    for dataset, rows, fields, duplicate_keys in tables:
        path = interim_root / f"{dataset}.csv"
        _write_csv(path, rows, fields)
        warning_count = sum(row["quality_status"] != "PASS" for row in rows)
        calendar_gaps = _calendar_gaps(rows)
        outputs.append(TableResult(dataset, path, len(rows), warning_count))
        times = [
            row.get("observed_date") or row.get("valid_date") or row.get("valid_time_local")
            for row in rows
        ]
        quality_rows.append(
            {
                "dataset": dataset,
                "records": len(rows),
                "duplicate_records": _duplicates(rows, duplicate_keys),
                "records_with_warnings": warning_count,
                "missing_calendar_dates": (
                    len(calendar_gaps) if calendar_gaps is not None else None
                ),
                "missing_calendar_date_values": (
                    "; ".join(calendar_gaps) if calendar_gaps is not None else None
                ),
                "earliest_time": min(times) if times else None,
                "latest_time": max(times) if times else None,
            }
        )
    quality_path = interim_root / "quality" / "quality_summary.csv"
    quality_fields = [
        "dataset", "records", "duplicate_records", "records_with_warnings",
        "missing_calendar_dates", "missing_calendar_date_values",
        "earliest_time", "latest_time",
    ]
    _write_csv(quality_path, quality_rows, quality_fields)
    outputs.append(
        TableResult(
            "quality_summary",
            quality_path,
            len(quality_rows),
            sum(row["records_with_warnings"] for row in quality_rows),
        )
    )
    return outputs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normaliza las últimas extracciones raw en tablas CSV interim."
    )
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--interim-root", type=Path, default=DEFAULT_INTERIM_ROOT)
    parser.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    outputs = transform_interim(args.raw_root, args.interim_root, args.external_root)
    print("Transformación completada.")
    for output in outputs:
        print(
            f"- {output.dataset}: {output.record_count} filas, "
            f"{output.warning_count} avisos -> {output.path}"
        )


if __name__ == "__main__":
    main()
