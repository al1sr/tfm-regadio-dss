"""Extracción histórica de SiAR respetando su cuota de registros por minuto."""

from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol

from src.data.extract_pilot import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SIAR_STATION,
    ExtractionFile,
    _safe_identifier,
    _write_raw_json,
)
from src.data.siar_client import SiARClient, SiARError


DEFAULT_CHUNK_DAYS = 90
DEFAULT_PAUSE_SECONDS = 60.0


class SiARHistorySource(Protocol):
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
    ) -> list[dict]: ...


def _date_chunks(start_date: date, end_date: date, chunk_days: int):
    if chunk_days < 1:
        raise ValueError("El tamaño de bloque debe ser positivo.")
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def extract_siar_history(
    *,
    start_date: date,
    end_date: date,
    station: str = DEFAULT_SIAR_STATION,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    client: SiARHistorySource | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
) -> ExtractionFile:
    """Descarga un periodo largo en bloques y genera un único sobre raw."""
    if start_date > end_date:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")
    if pause_seconds < 0:
        raise ValueError("La pausa no puede ser negativa.")
    station_code = _safe_identifier(station, "estación SiAR")
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("La fecha de ingestión debe incluir zona horaria.")

    source = client or SiARClient()
    records: list[dict] = []
    chunks = list(_date_chunks(start_date, end_date, chunk_days))
    for index, (chunk_start, chunk_end) in enumerate(chunks):
        if index:
            sleep_fn(pause_seconds)
        try:
            records.extend(
                source.get_data(
                    "Diarios",
                    "ESTACION",
                    station_code,
                    chunk_start,
                    chunk_end,
                    calculated=True,
                )
            )
        except SiARError as exc:
            raise SiARError(
                "No se pudo completar el bloque histórico "
                f"{chunk_start.isoformat()} a {chunk_end.isoformat()}: {exc}"
            ) from None

    unique: dict[tuple[str, str], dict] = {}
    for record in records:
        key = (str(record.get("Estacion", station_code)), str(record.get("Fecha", "")))
        unique[key] = record
    ordered = sorted(unique.values(), key=lambda item: str(item.get("Fecha", "")))

    run_id = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = (
        output_root
        / "siar"
        / "weather"
        / "daily"
        / f"station={station_code}"
        / f"period={start_date.isoformat()}_{end_date.isoformat()}"
        / f"history__{run_id}.json"
    )
    return _write_raw_json(
        path,
        source="SiAR",
        dataset="weather_daily",
        query={
            "station": station_code,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "calculated": True,
            "chunk_days": chunk_days,
            "chunk_count": len(chunks),
            "pause_seconds": pause_seconds,
        },
        payload=ordered,
        ingested_at=timestamp,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrae históricos diarios SiAR por bloques de cuota segura."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--station", default=DEFAULT_SIAR_STATION)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--chunk-days", type=int, default=DEFAULT_CHUNK_DAYS)
    parser.add_argument("--pause-seconds", type=float, default=DEFAULT_PAUSE_SECONDS)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    output = extract_siar_history(
        start_date=args.start_date,
        end_date=args.end_date,
        station=args.station,
        output_root=args.output_root,
        chunk_days=args.chunk_days,
        pause_seconds=args.pause_seconds,
    )
    print(
        "Histórico SiAR completado: "
        f"{output.record_count} registros -> {output.path}"
    )


if __name__ == "__main__":
    main()
