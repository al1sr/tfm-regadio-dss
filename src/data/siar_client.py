"""Cliente mínimo para consultar la API pública de SiAR.

La credencial se obtiene de la variable de entorno ``SIAR_API_TOKEN``.
El token nunca se incluye en mensajes de error ni se escribe en los logs.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests
from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://servicio.mapa.gob.es/siarapi/API/V1"
DEFAULT_TIMEOUT_SECONDS = 30


class SiARError(RuntimeError):
    """Error controlado al comunicarse con la API de SiAR."""


class SiARClient:
    """Realiza consultas autenticadas a SiAR sin exponer el token."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        load_dotenv()
        resolved_token = token or os.getenv("SIAR_API_TOKEN")
        if not resolved_token:
            raise ValueError(
                "No se ha configurado SIAR_API_TOKEN en el fichero .env."
            )

        self._token = resolved_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()

    def _get_json(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        request_params = dict(params or {})
        request_params["token"] = self._token

        try:
            response = self._session.get(
                f"{self._base_url}/{endpoint.lstrip('/')}",
                params=request_params,
                timeout=self._timeout,
            )
        except requests.RequestException:
            raise SiARError(
                "No se ha podido conectar con el servicio de SiAR."
            ) from None

        try:
            payload = response.json()
        except ValueError as exc:
            raise SiARError(
                f"SiAR devolvió una respuesta no válida (HTTP {response.status_code})."
            ) from exc

        if not isinstance(payload, dict):
            raise SiARError("SiAR devolvió un formato de respuesta inesperado.")

        if response.status_code != 200:
            message = payload.get("MensajeRespuesta") or "petición rechazada"
            raise SiARError(
                f"SiAR no pudo completar la consulta (HTTP {response.status_code}): "
                f"{message}"
            )

        return payload

    def get_info(self, information_type: str) -> list[dict[str, Any]]:
        """Consulta uno de los catálogos del endpoint ``Info`` de SiAR."""
        allowed_types = {
            "CCAA",
            "PROVINCIAS",
            "ESTACIONES",
            "ACCESOS",
            "CODIGOSVALIDACION",
        }
        normalized_type = information_type.upper()
        if normalized_type not in allowed_types:
            raise ValueError(
                "Tipo de información no válido. Valores admitidos: "
                + ", ".join(sorted(allowed_types))
            )

        payload = self._get_json(f"Info/{normalized_type}")
        records = payload.get("datos")
        if not isinstance(records, list):
            raise SiARError("La respuesta de SiAR no contiene una lista en 'datos'.")
        return records

    def get_access_limits(self) -> dict[str, Any]:
        """Devuelve los contadores y límites de uso asociados al token."""
        records = self.get_info("ACCESOS")
        if not records or not isinstance(records[0], dict):
            raise SiARError("SiAR no devolvió información sobre los accesos.")
        return records[0]

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
    ) -> list[dict[str, Any]]:
        """Consulta series agroclimáticas por estación, provincia o comunidad.

        ``identifiers`` puede contener uno o varios códigos obtenidos mediante
        los catálogos del endpoint ``Info``.
        """
        data_types = {
            "HORARIOS": "Horarios",
            "DIARIOS": "Diarios",
            "SEMANALES": "Semanales",
            "MENSUALES": "Mensuales",
        }
        scopes = {"CCAA", "PROVINCIA", "ESTACION"}
        normalized_type = data_type.upper()
        normalized_scope = scope.upper()
        if normalized_type not in data_types:
            raise ValueError(
                "Tipo de datos no válido. Valores admitidos: "
                + ", ".join(data_types.values())
            )
        if normalized_scope not in scopes:
            raise ValueError(
                "Ámbito no válido. Valores admitidos: "
                + ", ".join(sorted(scopes))
            )

        ids = [identifiers] if isinstance(identifiers, str) else identifiers
        if not ids:
            raise ValueError("Debe indicarse al menos un identificador.")

        params: dict[str, Any] = {
            "Id": ids,
            "FechaInicial": self._format_date(start_date),
            "FechaFinal": self._format_date(end_date),
        }
        if normalized_type != "HORARIOS":
            params["DatosCalculados"] = str(calculated).lower()
        if last_modified is not None:
            params["FechaUltModificacion"] = self._format_date(last_modified)

        payload = self._get_json(
            f"Datos/{data_types[normalized_type]}/{normalized_scope}", params
        )
        records = payload.get("datos")
        if not isinstance(records, list):
            raise SiARError("La respuesta de SiAR no contiene una lista en 'datos'.")
        return records

    @staticmethod
    def _format_date(value: str | date) -> str:
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError):
            raise ValueError("Las fechas deben usar el formato YYYY-MM-DD.") from None


def main() -> None:
    """Comprueba el acceso mostrando únicamente contadores no sensibles."""
    try:
        limits = SiARClient().get_access_limits()
    except (SiARError, ValueError) as exc:
        print(f"No se pudo completar la comprobación: {exc}")
        raise SystemExit(1) from None
    labels = {
        "NumAccesosMinutoActual": "Peticiones realizadas este minuto",
        "MaxAccesosMinuto": "Máximo de peticiones por minuto",
        "NumAccesosDiaActual": "Peticiones realizadas hoy",
        "MaxAccesosDia": "Máximo de peticiones por día",
        "RegistrosAcumuladosMinuto": "Registros obtenidos este minuto",
        "MaxRegistrosMinuto": "Máximo de registros por minuto",
        "RegistrosAcumuladosDia": "Registros obtenidos hoy",
        "MaxRegistrosDia": "Máximo de registros por día",
    }
    print("Conexión con SiAR correcta.")
    for field, label in labels.items():
        print(f"{label}: {limits.get(field, 'no informado')}")


if __name__ == "__main__":
    main()
