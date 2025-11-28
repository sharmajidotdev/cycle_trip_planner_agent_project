import unittest
from unittest.mock import patch

from models.schemas import ElevationRequest
from tools.elevation import get_elevation_profile


class ElevationTests(unittest.IsolatedAsyncioTestCase):
    async def test_elevation_profile_is_deterministic_when_random_patched(self):
        req = ElevationRequest(location="Alps", day=1)
        with patch("tools.elevation.random.randint", return_value=0):
            response = await get_elevation_profile(req)

        profile = response.profile[0]
        self.assertEqual(profile.location, "Alps")
        self.assertEqual(profile.elevation_gain_m, 404.0)
        self.assertEqual(profile.elevation_loss_m, 242.0)
        self.assertEqual(profile.difficulty, "moderate")


if __name__ == "__main__":
    unittest.main()
