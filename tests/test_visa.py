import unittest

from models.schemas import VisaRequest
from tools.visa import check_visa_requirements


class VisaTests(unittest.IsolatedAsyncioTestCase):
    async def test_known_visa_free_pair(self):
        req = VisaRequest(nationality="USA", destination_country="Spain")
        response = await check_visa_requirements(req)

        self.assertFalse(response.requirement.required)
        self.assertEqual(response.requirement.allowed_stay_days, 90)
        self.assertIsNone(response.requirement.type)

    async def test_requires_visa_for_unknown_pair(self):
        req = VisaRequest(nationality="Brazil", destination_country="China")
        response = await check_visa_requirements(req)

        self.assertTrue(response.requirement.required)
        self.assertEqual(response.requirement.type, "tourist")
        self.assertEqual(response.requirement.allowed_stay_days, 30)


if __name__ == "__main__":
    unittest.main()
