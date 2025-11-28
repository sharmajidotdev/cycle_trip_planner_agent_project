import unittest

from models.schemas import AccommodationOption, BudgetRequest
from tools.budget import estimate_budget


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_estimate_budget_uses_itinerary_costs(self):
        itinerary = [
            {"accommodation": [AccommodationOption(name="Hostel A", price_per_night=80.0, type="hostel", available=True)]},
            {"accommodation": [AccommodationOption(name="BnB B", price_per_night=60.0, type="bnb", available=True)]},
        ]
        req = BudgetRequest(currency="usd", travelers=1)

        response = await estimate_budget(req, itinerary)

        self.assertEqual(response.currency, "USD")
        self.assertAlmostEqual(response.breakdown.lodging_total, 140.0)
        self.assertAlmostEqual(response.total, 262.5)
        self.assertAlmostEqual(response.per_day, 131.25)


if __name__ == "__main__":
    unittest.main()
