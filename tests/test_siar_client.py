"""Pruebas unitarias del cliente de SiAR sin realizar llamadas reales."""

import unittest
from unittest.mock import Mock, patch

from src.data.siar_client import SiARClient, SiARError


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class SiARClientTests(unittest.TestCase):
    @patch("src.data.siar_client.load_dotenv")
    @patch("src.data.siar_client.os.getenv", return_value=None)
    def test_requires_token(self, _getenv, _load_dotenv):
        with self.assertRaisesRegex(ValueError, "SIAR_API_TOKEN"):
            SiARClient()

    def test_reads_access_limits(self):
        session = Mock()
        expected = {"NumAccesosDiaActual": 2, "MaxAccesosDia": 1000}
        session.get.return_value = FakeResponse(200, {"datos": [expected]})

        result = SiARClient(token="secret", session=session).get_access_limits()

        self.assertEqual(result, expected)
        _, kwargs = session.get.call_args
        self.assertEqual(kwargs["params"], {"token": "secret"})

    def test_does_not_expose_token_in_api_error(self):
        session = Mock()
        session.get.return_value = FakeResponse(
            403, {"MensajeRespuesta": "Límite de accesos superado"}
        )

        with self.assertRaises(SiARError) as context:
            SiARClient(token="secret-token", session=session).get_access_limits()

        self.assertNotIn("secret-token", str(context.exception))
        self.assertIn("HTTP 403", str(context.exception))

    def test_rejects_unknown_information_type(self):
        with self.assertRaisesRegex(ValueError, "Tipo de información no válido"):
            SiARClient(token="secret").get_info("desconocido")

    def test_builds_daily_station_query(self):
        session = Mock()
        session.get.return_value = FakeResponse(200, {"datos": [{"Estacion": "AL01"}]})

        result = SiARClient(token="secret", session=session).get_data(
            "diarios",
            "estacion",
            "AL01",
            "2025-01-01",
            "2025-01-02",
            calculated=True,
        )

        self.assertEqual(result, [{"Estacion": "AL01"}])
        _, kwargs = session.get.call_args
        self.assertEqual(
            kwargs["params"],
            {
                "Id": ["AL01"],
                "FechaInicial": "2025-01-01",
                "FechaFinal": "2025-01-02",
                "DatosCalculados": "true",
                "token": "secret",
            },
        )

    def test_rejects_invalid_date_format(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            SiARClient(token="secret").get_data(
                "diarios", "estacion", "AL01", "01/01/2025", "2025-01-02"
            )


if __name__ == "__main__":
    unittest.main()
