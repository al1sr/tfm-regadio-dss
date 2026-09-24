"""Extracción reproducible de las fuentes del piloto de riego.

Guarda respuestas de SiAR y AEMET en ``data/raw`` sin transformarlas. Cada
archivo incluye la consulta, la fecha de ingestión y el número de registros,
pero nunca credenciales ni URLs temporales de descarga.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from src.data.aemet_client import AEMETClient
from src.data.siar_client import SiARClient


DEFAULT_OUTPUT_ROOT = Path("data/raw")
DEFAULT_SIAR_STATION = "AL01"
DEFAULT_AEMET_MUNICIPALITY = "04013"


class SiARSource(Protocol):
    def get_info(self, information_type: str) -> list[dict[str, Any]]: ...

    def get_data(
        self,
        data_type: str,
        scope: str,
        identifiers: str | list[str],
        start_date: str | date,
        end_date: str | date,
        *,
        calculated: bool = False,
        last_modified: str | date | None = None,
    ) -> list[dict[str, Any]]: ...


class AEMETSource(Protocol):
    def get_municipalities(self) -> dict[str, Any] | list[Any]: ...

    def get_climate_stations(self) -> dict[str, Any] | list[Any]: ...

    def get_daily_municipality_forecast(
        self, municipality_code: str
    ) -> dict[str, Any] | list[Any]: ...

    def get_hourly_municipality_forecast(
        self, municipality_code: str
    ) -> dict[str, Any] | list[Any]: ...


@dataclass(frozen=True)
class ExtractionFile:
    dataset: str
    path: Path
    record_count: int


def _safe_identifier(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"El identificador de {label} no es válido.")
    return value


def _record_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return 1
    return 0


def _write_raw_json(
    path: Path,
    *,
    source: str,
    dataset: str,
    query: dict[str, Any],
    payload: Any,
    ingested_at: datetime,
) -> ExtractionFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = _record_count(payload)
    envelope = {
        "schema_version": 1,
        "source": source,
        "dataset": dataset,
        "ingested_at": ingested_at.isoformat(),
        "query": query,
        "record_count": count,
        "data": payload,
    }
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return ExtractionFile(dataset=dataset, path=path, record_count=count)


def extract_pilot(
    *,
    start_date: date,
    end_date: date,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    siar_station: str = DEFAULT_SIAR_STATION,
    aemet_municipality: str = DEFAULT_AEMET_MUNICIPALITY,
    include_siar_catalogs: bool = False,
    include_aemet_catalogs: bool = False,
    catalogs_only: bool = False,
    siar_client: SiARSource | None = None,
    aemet_client: AEMETSource | None = None,
    now: datetime | None = None,
) -> list[ExtractionFile]:
    """Extrae una muestra del piloto y devuelve el inventario de archivos."""
    if start_date > end_date:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")
    if catalogs_only and not (include_siar_catalogs or include_aemet_catalogs):
        raise ValueError(
            "El modo de solo catálogos requiere seleccionar al menos un catálogo."
        )
    station = _safe_identifier(siar_station, "estación SiAR")
    municipality = _safe_identifier(aemet_municipality, "municipio AEMET")
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("La fecha de ingestión debe incluir zona horaria.")

    siar = siar_client or SiARClient()
    aemet = aemet_client or AEMETClient()
    day_partition = timestamp.astimezone(timezone.utc).date().isoformat()
    run_id = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outputs: list[ExtractionFile] = []

    if include_siar_catalogs:
        stations = siar.get_info("ESTACIONES")
        outputs.append(
            _write_raw_json(
                output_root
                / "siar"
                / "catalogs"
                / f"date={day_partition}"
                / f"stations__{run_id}.json",
                source="SiAR",
                dataset="stations",
                query={"information_type": "ESTACIONES"},
                payload=stations,
                ingested_at=timestamp,
            )
        )

        validation_codes = siar.get_info("CODIGOSVALIDACION")
        outputs.append(
            _write_raw_json(
                output_root
                / "siar"
                / "catalogs"
                / f"date={day_partition}"
                / f"validation_codes__{run_id}.json",
                source="SiAR",
                dataset="validation_codes",
                query={"information_type": "CODIGOSVALIDACION"},
                payload=validation_codes,
                ingested_at=timestamp,
            )
        )

    if not catalogs_only:
        daily_records = siar.get_data(
            "Diarios",
            "ESTACION",
            station,
            start_date,
            end_date,
            calculated=True,
        )
        outputs.append(
            _write_raw_json(
                output_root
                / "siar"
                / "weather"
                / "daily"
                / f"station={station}"
                / f"year={end_date.year:04d}"
                / f"month={end_date.month:02d}"
                / f"{start_date.isoformat()}_{end_date.isoformat()}__{run_id}.json",
                source="SiAR",
                dataset="weather_daily",
                query={
                    "station": station,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "calculated": True,
                },
                payload=daily_records,
                ingested_at=timestamp,
            )
        )

    if include_aemet_catalogs:
        municipalities = aemet.get_municipalities()
        outputs.append(
            _write_raw_json(
                output_root
                / "aemet"
                / "catalogs"
                / f"date={day_partition}"
                / f"municipalities__{run_id}.json",
                source="AEMET",
                dataset="municipalities",
                query={},
                payload=municipalities,
                ingested_at=timestamp,
            )
        )

        climate_stations = aemet.get_climate_stations()
        outputs.append(
            _write_raw_json(
                output_root
                / "aemet"
                / "catalogs"
                / f"date={day_partition}"
                / f"climate_stations__{run_id}.json",
                source="AEMET",
                dataset="climate_stations",
                query={},
                payload=climate_stations,
                ingested_at=timestamp,
            )
        )

    if not catalogs_only:
        daily_forecast = aemet.get_daily_municipality_forecast(municipality)
        outputs.append(
            _write_raw_json(
                output_root
                / "aemet"
                / "forecast"
                / "daily"
                / f"municipality={municipality}"
                / f"ingestion_date={day_partition}"
                / f"{run_id}.json",
                source="AEMET",
                dataset="forecast_daily",
                query={"municipality": municipality},
                payload=daily_forecast,
                ingested_at=timestamp,
            )
        )

        hourly_forecast = aemet.get_hourly_municipality_forecast(municipality)
        outputs.append(
            _write_raw_json(
                output_root
                / "aemet"
                / "forecast"
                / "hourly"
                / f"municipality={municipality}"
                / f"ingestion_date={day_partition}"
                / f"{run_id}.json",
                source="AEMET",
                dataset="forecast_hourly",
                query={"municipality": municipality},
                payload=hourly_forecast,
                ingested_at=timestamp,
            )
        )
    return outputs


def _parse_args() -> argparse.Namespace:
    yesterday = date.today() - timedelta(days=1)
    default_start = yesterday - timedelta(days=6)
    parser = argparse.ArgumentParser(
        description="Extrae la muestra inicial de SiAR y AEMET para el piloto."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=default_start)
    parser.add_argument("--end-date", type=date.fromisoformat, default=yesterday)
    parser.add_argument("--siar-station", default=DEFAULT_SIAR_STATION)
    parser.add_argument("--aemet-municipality", default=DEFAULT_AEMET_MUNICIPALITY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--include-siar-catalogs",
        action="store_true",
        help="Descarga los catálogos SiAR; ejecutar por separado por su cuota.",
    )
    parser.add_argument(
        "--include-aemet-catalogs",
        action="store_true",
        help="Descarga los catálogos de municipios y estaciones AEMET.",
    )
    parser.add_argument(
        "--catalogs-only",
        action="store_true",
        help="Descarga solo los catálogos seleccionados, sin series ni predicciones.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    outputs = extract_pilot(
        start_date=args.start_date,
        end_date=args.end_date,
        output_root=args.output_root,
        siar_station=args.siar_station,
        aemet_municipality=args.aemet_municipality,
        include_siar_catalogs=args.include_siar_catalogs,
        include_aemet_catalogs=args.include_aemet_catalogs,
        catalogs_only=args.catalogs_only,
    )
    print("Extracción completada sin publicar credenciales.")
    for output in outputs:
        print(f"- {output.dataset}: {output.record_count} registros -> {output.path}")


if __name__ == "__main__":
    main()
