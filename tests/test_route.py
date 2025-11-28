import unittest
from unittest.mock import AsyncMock, patch

from models.schemas import RouteRequest
from tools.route import get_route


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_route_falls_back_to_mock_when_osrm_unavailable(self):
        req = RouteRequest(start="A", end="B", daily_distance_km=80)
        with patch("tools.route._fetch_osrm_route", new=AsyncMock(return_value=None)):
            response = await get_route(req)

        self.assertGreaterEqual(response.total_distance_km, 160.0)
        self.assertEqual(response.days, 3)
        self.assertEqual(response.segments[0].start, "A")
        self.assertEqual(response.segments[-1].end, "B")

    async def test_get_route_uses_osrm_data_when_available(self):
        req = RouteRequest(start="Start", end="Finish", daily_distance_km=50)
        mock_route = {
            "distance": 120000,
            "geometry": {"coordinates": [[0, 0], [0, 1], [0, 2]]},
        }
        stop_names = ["Town 1", "Town 2", "Town 3"]
        with patch("tools.route._fetch_osrm_route", new=AsyncMock(return_value=mock_route)), patch(
            "tools.route._label_stops_with_towns", new=AsyncMock(return_value=stop_names)
        ):
            response = await get_route(req)

        self.assertEqual(response.total_distance_km, 120.0)
        self.assertEqual(response.days, 3)
        self.assertEqual(response.segments[0].end, "Town 1")
        self.assertEqual(response.segments[1].end, "Town 2")
        self.assertEqual(response.segments[-1].end, "Finish")
        self.assertIn("Based on OSRM bike routing.", response.segments[0].notes or "")


if __name__ == "__main__":
    unittest.main()
