import unittest
from unittest.mock import patch

from tests.helpers import MockAsyncClient, MockResponse
from tools.geocoding import geocode_location, reverse_geocode


class GeocodingTests(unittest.IsolatedAsyncioTestCase):
    async def test_geocode_location_returns_none_for_blank(self):
        result = await geocode_location("")
        self.assertIsNone(result)

    async def test_geocode_location_success(self):
        payload = {
            "results": [
                {
                    "name": "Paris",
                    "latitude": 48.85,
                    "longitude": 2.35,
                    "country": "France",
                    "timezone": "Europe/Paris",
                }
            ]
        }
        response = MockResponse(payload)
        with patch("tools.geocoding.httpx.AsyncClient", return_value=MockAsyncClient(response)):
            result = await geocode_location("Paris")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Paris")
        self.assertAlmostEqual(result["lat"], 48.85)
        self.assertEqual(result["country"], "France")

    async def test_reverse_geocode_returns_none_on_404(self):
        response = MockResponse({}, status_code=404)
        with patch("tools.geocoding.httpx.AsyncClient", return_value=MockAsyncClient(response)):
            result = await reverse_geocode(0.0, 0.0)

        self.assertIsNone(result)

    async def test_reverse_geocode_success(self):
        payload = {
            "results": [
                {
                    "name": "Testtown",
                    "admin1": "Region",
                    "country": "Exampleland",
                    "latitude": 10.5,
                    "longitude": 20.5,
                }
            ]
        }
        response = MockResponse(payload)
        with patch("tools.geocoding.httpx.AsyncClient", return_value=MockAsyncClient(response)):
            result = await reverse_geocode(10.5, 20.5)

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Testtown")
        self.assertEqual(result["admin1"], "Region")
        self.assertEqual(result["country"], "Exampleland")


if __name__ == "__main__":
    unittest.main()
