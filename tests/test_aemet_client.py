"""Pruebas unitarias del cliente AEMET sin realizar llamadas reales."""

import unittest
from unittest.mock import Mock, patch

from src.data.aemet_client import AEMETClient, AEMETError


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeEncodedResponse:
    status_code = 200

    def __init__(self, content):
        self.content = content


class AEMETClientTests(unittest.TestCase):
    @patch("src.data.aemet_client.load_dotenv")
    @patch("src.data.aemet_client.os.getenv", return_value=None)
    def test_requires_api_key(self, _getenv, _load_dotenv):
        with self.assertRaisesRegex(ValueError, "AEMET_API_KEY"):
            AEMETClient()

    def test_resolves_two_step_download_without_forwarding_key(self):
        session = Mock()
        session.get.side_effect = [
            FakeResponse(
                200,
                {
                    "estado": 200,
                    "datos": "https://opendata.aemet.es/opendata/sh/example",
                },
            ),
            FakeResponse(200, [{"nombre": "Almería"}]),
        ]

        result = AEMETClient(api_key="secret", session=session).get_municipalities()

        self.assertEqual(result, [{"nombre": "Almería"}])
        first_call, second_call = session.get.call_args_list
        self.assertEqual(first_call.kwargs["headers"], {"api_key": "secret"})
        self.assertIsNone(second_call.kwargs["headers"])

    def test_builds_daily_climatology_endpoint(self):
        session = Mock()
        session.get.side_effect = [
            FakeResponse(
                200,
                {
                    "datos": "https://opendata.aemet.es/opendata/sh/climate",
                },
            ),
            FakeResponse(200, []),
        ]

        AEMETClient(api_key="secret", session=session).get_daily_climatology(
            ["6325O", "6297"], "2026-09-01", "2026-09-02"
        )

        requested_url = session.get.call_args_list[0].args[0]
        self.assertIn("fechaini/2026-09-01T00:00:00UTC", requested_url)
        self.assertIn("fechafin/2026-09-02T00:00:00UTC", requested_url)
        self.assertTrue(requested_url.endswith("/estacion/6325O,6297"))

    def test_rejects_untrusted_download_url(self):
        session = Mock()
        session.get.return_value = FakeResponse(
            200, {"datos": "https://example.com/untrusted"}
        )

        with self.assertRaisesRegex(AEMETError, "URL de descarga no permitida"):
            AEMETClient(api_key="secret", session=session).get_municipalities()

    def test_does_not_expose_key_in_error(self):
        session = Mock()
        session.get.return_value = FakeResponse(
            401, {"descripcion": "API key no válida"}
        )

        with self.assertRaises(AEMETError) as context:
            AEMETClient(api_key="secret-key", session=session).get_municipalities()

        self.assertNotIn("secret-key", str(context.exception))

    def test_rejects_invalid_municipality_code(self):
        with self.assertRaisesRegex(ValueError, "municipio"):
            AEMETClient(api_key="secret").get_daily_municipality_forecast("04/013")

    def test_decodes_legacy_aemet_encoding(self):
        session = Mock()
        session.get.side_effect = [
            FakeResponse(
                200,
                {"datos": "https://opendata.aemet.es/opendata/sh/stations"},
            ),
            FakeEncodedResponse('[{"nombre":"ALMERÍA"}]'.encode("iso-8859-15")),
        ]

        result = AEMETClient(api_key="secret", session=session).get_climate_stations()

        self.assertEqual(result, [{"nombre": "ALMERÍA"}])


if __name__ == "__main__":
    unittest.main()
