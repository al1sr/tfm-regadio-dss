"""Genera una auditoría reproducible de volumen y calidad para el apartado 4.1."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable


DEFAULT_RAW_ROOT = Path("data/raw")
DEFAULT_EXTERNAL_ROOT = Path("data/external")
DEFAULT_INTERIM_ROOT = Path("data/interim")
DEFAULT_PROCESSED = Path("data/processed/modeling_dataset_daily.csv")
DEFAULT_OUTPUT = Path("docs/data_samples/etl_volume_summary_4_1.csv")

OUTPUT_FIELDS = [
    "stage",
    "dataset",
    "source",
    "rows",
    "columns",
    "valid_target_rows",
    "pass_rows",
    "warning_rows",
    "duplicate_rows",
    "missing_calendar_dates",
    "file_size_bytes",
    "notes",
]


def _latest(paths: Iterable[Path], description: str) -> Path:
    candidates = list(paths)
    if not candidates:
        raise FileNotFoundError(f"No se encontró {description}.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _read_csv(path: Path, delimiter: str = ",") -> tuple[list[dict[str, str]], int]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=delimiter)
        rows = list(reader)
        return rows, len(reader.fieldnames or [])


def _duplicate_count(rows: list[dict[str, str]], keys: tuple[str, ...]) -> int:
    if not rows:
        return 0
    counts = Counter(tuple(row.get(key, "") for key in keys) for row in rows)
    return sum(count - 1 for count in counts.values() if count > 1)


def _quality_counts(rows: list[dict[str, str]]) -> tuple[int, int]:
    statuses = Counter(row.get("quality_status", "").upper() for row in rows)
    return statuses["PASS"], statuses["WARN"]


def _missing_date_count(rows: list[dict[str, str]], date_column: str) -> int:
    observed = {
        date.fromisoformat(row[date_column])
        for row in rows
        if row.get(date_column, "").strip()
    }
    if not observed:
        return 0
    expected: set[date] = set()
    current = min(observed)
    while current <= max(observed):
        expected.add(current)
        current += timedelta(days=1)
    return len(expected - observed)


def _raw_profile(path: Path, dataset: str, source: str, notes: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "stage": "raw",
        "dataset": dataset,
        "source": source,
        "rows": int(payload.get("record_count", len(payload.get("data", [])))),
        "columns": "",
        "valid_target_rows": "",
        "pass_rows": "",
        "warning_rows": "",
        "duplicate_rows": "",
        "missing_calendar_dates": "",
        "file_size_bytes": path.stat().st_size,
        "notes": notes,
    }


def _table_profile(
    path: Path,
    dataset: str,
    source: str,
    keys: tuple[str, ...],
    date_column: str | None = None,
    target: str | None = None,
    notes: str = "",
) -> dict[str, object]:
    rows, columns = _read_csv(path)
    pass_rows, warning_rows = _quality_counts(rows)
    missing_calendar_dates: int | str = ""
    if date_column:
        missing_calendar_dates = _missing_date_count(rows, date_column)
    valid_target_rows: int | str = ""
    if target:
        valid_target_rows = sum(
            1 for row in rows if row.get(target, "").strip() not in {"", "nan", "NaN"}
        )
    return {
        "stage": "processed" if path.name == DEFAULT_PROCESSED.name else "interim",
        "dataset": dataset,
        "source": source,
        "rows": len(rows),
        "columns": columns,
        "valid_target_rows": valid_target_rows,
        "pass_rows": pass_rows,
        "warning_rows": warning_rows,
        "duplicate_rows": _duplicate_count(rows, keys),
        "missing_calendar_dates": missing_calendar_dates,
        "file_size_bytes": path.stat().st_size,
        "notes": notes,
    }


def build_audit(
    raw_root: Path = DEFAULT_RAW_ROOT,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
    interim_root: Path = DEFAULT_INTERIM_ROOT,
    processed_path: Path = DEFAULT_PROCESSED,
) -> list[dict[str, object]]:
    """Resume las capas del piloto sin mezclar catálogos con series analíticas."""
    siar_history = _latest(
        raw_root.glob("siar/weather/daily/station=*/period=*/history__*.json"),
        "el histórico SiAR del piloto",
    )
    crop_source = _latest(
        external_root.glob("siar_necesidades_*.csv"),
        "el CSV de necesidades hídricas",
    )
    aemet_daily = _latest(
        raw_root.glob("aemet/forecast/daily/municipality=*/*/*.json"),
        "la predicción diaria AEMET",
    )
    aemet_hourly = _latest(
        raw_root.glob("aemet/forecast/hourly/municipality=*/*/*.json"),
        "la predicción horaria AEMET",
    )

    crop_rows, crop_columns = _read_csv(crop_source, delimiter=";")
    profiles: list[dict[str, object]] = [
        _raw_profile(
            siar_history,
            "siar_weather_daily",
            "SiAR API",
            "Observaciones diarias de la estación y periodo seleccionados.",
        ),
        {
            "stage": "raw_external",
            "dataset": "siar_crop_water_needs",
            "source": "SiAR web",
            "rows": len(crop_rows),
            "columns": crop_columns,
            "valid_target_rows": "",
            "pass_rows": "",
            "warning_rows": "",
            "duplicate_rows": "",
            "missing_calendar_dates": "",
            "file_size_bytes": crop_source.stat().st_size,
            "notes": "CSV oficial dependiente de estación, comarca, cultivo y periodo.",
        },
        _raw_profile(
            aemet_daily,
            "aemet_forecast_daily_root",
            "AEMET OpenData",
            "Un objeto municipal que se despliega en siete fechas válidas.",
        ),
        _raw_profile(
            aemet_hourly,
            "aemet_forecast_hourly_root",
            "AEMET OpenData",
            "Un objeto municipal que se despliega en 48 instantes horarios.",
        ),
    ]

    profiles.extend(
        [
            _table_profile(
                interim_root / "siar_weather_daily.csv",
                "siar_weather_daily",
                "SiAR API",
                ("station_code", "observed_date"),
                date_column="observed_date",
                target="et0_pm_mm",
                notes="150 filas conservadas; 148 con ET0 válida.",
            ),
            _table_profile(
                interim_root / "siar_crop_water_needs_daily.csv",
                "siar_crop_water_needs_daily",
                "SiAR web",
                ("station_code", "crop", "observed_date"),
                date_column="observed_date",
                target="net_irrigation_need_mm",
                notes="150 filas conservadas; 148 con necesidad neta válida.",
            ),
            _table_profile(
                interim_root / "aemet_forecast_daily.csv",
                "aemet_forecast_daily",
                "AEMET OpenData",
                ("municipality_code", "issued_at", "valid_date"),
                notes="El objeto raíz se normaliza a una fila por fecha válida.",
            ),
            _table_profile(
                interim_root / "aemet_forecast_hourly.csv",
                "aemet_forecast_hourly",
                "AEMET OpenData",
                ("municipality_code", "issued_at", "valid_time_local"),
                notes="El objeto raíz se normaliza a una fila por instante válido.",
            ),
            _table_profile(
                processed_path,
                "modeling_dataset_daily",
                "SiAR integrado",
                ("station_code", "crop", "observed_date"),
                date_column="observed_date",
                target="target_net_irrigation_need_mm",
                notes="150 × 88; 148 etiquetas válidas para modelización.",
            ),
        ]
    )
    return profiles


def write_audit(rows: list[dict[str, object]], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera el resumen de volumen y calidad de las capas ETL del piloto."
    )
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    parser.add_argument("--interim-root", type=Path, default=DEFAULT_INTERIM_ROOT)
    parser.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = write_audit(
        build_audit(args.raw_root, args.external_root, args.interim_root, args.processed),
        args.output,
    )
    print(output)


if __name__ == "__main__":
    main()
