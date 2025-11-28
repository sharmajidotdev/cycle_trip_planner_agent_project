import unittest
from unittest.mock import AsyncMock, patch

from models.schemas import AccommodationRequest
from tests.helpers import MockAsyncClient, MockResponse
from tools.accomodation import find_accommodation


class AccommodationTests(unittest.IsolatedAsyncioTestCase):
    async def test_falls_back_to_mock_when_geocode_unavailable(self):
        req = AccommodationRequest(location="Nowhere", day=1)
        with patch("tools.accomodation.geocode_location", new=AsyncMock(return_value=None)):
            response = await find_accommodation(req)

        self.assertEqual(response.location, "Nowhere")
        self.assertEqual(response.day, 1)
        self.assertTrue(response.options)

    async def test_uses_api_results_when_available(self):
        req = AccommodationRequest(location="Berlin", day=2)
        geo = {"name": "Berlin", "lat": 52.5, "lon": 13.4}
        payload = {
            "elements": [
                {
                    "tags": {
                        "name": "Hotel One",
                        "tourism": "hotel",
                        "bicycle_parking": "yes",
                        "internet_access": "wlan",
                        "breakfast": "yes",
                    }
                }
            ]
        }
        response = MockResponse(payload)
        with patch("tools.accomodation.geocode_location", new=AsyncMock(return_value=geo)), patch(
            "tools.accomodation.httpx.AsyncClient", return_value=MockAsyncClient(response)
        ):
            result = await find_accommodation(req)

        self.assertEqual(result.location, "Berlin")
        self.assertTrue(result.options)
        self.assertTrue(any("Bike parking" in opt.notes or "Near" in opt.notes for opt in result.options))


if __name__ == "__main__":
    unittest.main()
