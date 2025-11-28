import unittest
from unittest.mock import AsyncMock, patch

from models.schemas import WeatherRequest
from tests.helpers import MockAsyncClient, MockResponse
from tools.weather import get_weather


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_mock_weather_when_geocode_fails(self):
        req = WeatherRequest(location="Cloud City", day=3)
        with patch("tools.weather.geocode_location", new=AsyncMock(return_value=None)):
            response = await get_weather(req)

        self.assertEqual(response.daily[0].location, "Cloud City")
        self.assertEqual(response.daily[0].day, 3)

    async def test_fetches_weather_from_api(self):
        req = WeatherRequest(location="Paris", day=2)
        geo = {"name": "Paris", "lat": 48.8, "lon": 2.3}
        payload = {
            "daily": {
                "time": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "temperature_2m_max": [21, 22, 23],
                "temperature_2m_min": [10, 11, 12],
                "precipitation_probability_max": [30, 40, 50],
                "weathercode": [0, 63, 3],
            }
        }
        response = MockResponse(payload)
        with patch("tools.weather.geocode_location", new=AsyncMock(return_value=geo)), patch(
            "tools.weather.httpx.AsyncClient", return_value=MockAsyncClient(response)
        ):
            result = await get_weather(req)

        forecast = result.daily[0]
        self.assertEqual(forecast.location, "Paris")
        self.assertEqual(forecast.day, 2)
        self.assertEqual(forecast.conditions, "rain")
        self.assertAlmostEqual(forecast.precipitation_chance, 0.4)


if __name__ == "__main__":
    unittest.main()
