import unittest

from models.schemas import POIRequest
from tools.poi import get_points_of_interest


class POITests(unittest.IsolatedAsyncioTestCase):
    async def test_points_of_interest_mocked_output(self):
        req = POIRequest(location="Kyoto", day=1)
        response = await get_points_of_interest(req)

        self.assertEqual(response.day, 1)
        self.assertEqual(response.location, "Kyoto")
        self.assertEqual(len(response.pois), 3)
        self.assertEqual(response.pois[0].relevance, "high")


if __name__ == "__main__":
    unittest.main()
