"""Cliente mínimo para AEMET OpenData.

AEMET devuelve primero un documento de control que contiene una URL temporal en
``datos``. El cliente resuelve automáticamente esa segunda descarga y mantiene
la API key fuera de URLs, mensajes de error y logs.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://opendata.aemet.es/opendata/api"
DEFAULT_TIMEOUT_SECONDS = 30


class AEMETError(RuntimeError):
    """Error controlado al comunicarse con AEMET OpenData."""


class AEMETClient:
    """Consulta productos de AEMET OpenData mediante su descarga en dos pasos."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        load_dotenv()
        resolved_key = api_key or os.getenv("AEMET_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No se ha configurado AEMET_API_KEY en el fichero .env."
            )

        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()

    def _request_json(
        self, url: str, *, authenticated: bool
    ) -> dict[str, Any] | list[Any]:
        headers = {"api_key": self._api_key} if authenticated else None
        try:
            response = self._session.get(
                url,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.RequestException:
            raise AEMETError("No se ha podido conectar con AEMET OpenData.") from None

        try:
            raw_content = getattr(response, "content", None)
            if isinstance(raw_content, bytes):
                payload = self._decode_json_bytes(raw_content)
            else:
                payload = response.json()
        except (UnicodeDecodeError, ValueError):
            raise AEMETError(
                f"AEMET devolvió una respuesta no válida (HTTP {response.status_code})."
            ) from None

        if response.status_code != 200:
            description = (
                payload.get("descripcion")
                if isinstance(payload, dict)
                else "petición rechazada"
            )
            raise AEMETError(
                f"AEMET no pudo completar la consulta (HTTP {response.status_code}): "
                f"{description or 'petición rechazada'}"
            )

        if not isinstance(payload, (dict, list)):
            raise AEMETError("AEMET devolvió un formato de respuesta inesperado.")
        return payload

    @staticmethod
    def _decode_json_bytes(content: bytes) -> dict[str, Any] | list[Any]:
        """Decodifica JSON aunque el producto use la codificación histórica de AEMET."""
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "iso-8859-15", "latin-1"):
            try:
                return json.loads(content.decode(encoding))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc
        if last_error is not None:
            raise ValueError("No se pudo decodificar la respuesta JSON.") from last_error
        raise ValueError("La respuesta JSON está vacía.")

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (
            hostname == "aemet.es" or hostname.endswith(".aemet.es")
        ):
            raise AEMETError("AEMET devolvió una URL de descarga no permitida.")

    def _get_product(self, endpoint: str) -> dict[str, Any] | list[Any]:
        control = self._request_json(
            f"{self._base_url}/{endpoint.lstrip('/')}", authenticated=True
        )
        if not isinstance(control, dict):
            raise AEMETError("La respuesta de control de AEMET no es válida.")

        data_url = control.get("datos")
        if not isinstance(data_url, str) or not data_url:
            description = control.get("descripcion") or "sin URL de descarga"
            raise AEMETError(f"AEMET no proporcionó datos: {description}")

        self._validate_download_url(data_url)
        return self._request_json(data_url, authenticated=False)

    def get_municipalities(self) -> dict[str, Any] | list[Any]:
        """Devuelve el catálogo de municipios y sus códigos."""
        return self._get_product("maestro/municipios")

    def get_climate_stations(self) -> dict[str, Any] | list[Any]:
        """Devuelve el inventario de estaciones climatológicas."""
        return self._get_product(
            "valores/climatologicos/inventarioestaciones/todasestaciones"
        )

    def get_daily_municipality_forecast(
        self, municipality_code: str
    ) -> dict[str, Any] | list[Any]:
        """Devuelve la predicción diaria del municipio indicado."""
        self._validate_code(municipality_code, "municipio")
        return self._get_product(
            f"prediccion/especifica/municipio/diaria/{municipality_code}"
        )

    def get_hourly_municipality_forecast(
        self, municipality_code: str
    ) -> dict[str, Any] | list[Any]:
        """Devuelve la predicción horaria, con horizonte de hasta 48 horas."""
        self._validate_code(municipality_code, "municipio")
        return self._get_product(
            f"prediccion/especifica/municipio/horaria/{municipality_code}"
        )

    def get_daily_climatology(
        self,
        station_codes: str | list[str],
        start_date: str | date,
        end_date: str | date,
    ) -> dict[str, Any] | list[Any]:
        """Devuelve observaciones climatológicas diarias de una o más estaciones."""
        codes = [station_codes] if isinstance(station_codes, str) else station_codes
        if not codes or any(not code or "," in code for code in codes):
            raise ValueError("Debe indicarse al menos un código de estación válido.")

        start = self._format_datetime(start_date)
        end = self._format_datetime(end_date)
        return self._get_product(
            "valores/climatologicos/diarios/datos/"
            f"fechaini/{start}/fechafin/{end}/estacion/{','.join(codes)}"
        )

    @staticmethod
    def _format_datetime(value: str | date) -> str:
        if isinstance(value, date):
            parsed = value
        else:
            try:
                parsed = date.fromisoformat(value)
            except (TypeError, ValueError):
                raise ValueError("Las fechas deben usar el formato YYYY-MM-DD.") from None
        return f"{parsed.isoformat()}T00:00:00UTC"

    @staticmethod
    def _validate_code(value: str, label: str) -> None:
        if not value or not value.isalnum():
            raise ValueError(f"El código de {label} no es válido.")
