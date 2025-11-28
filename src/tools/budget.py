from models.schemas import (
    AccommodationOption,
    BudgetBreakdown,
    BudgetRequest,
    BudgetResponse,
)


def _normalize_currency(cur: str | None) -> str:
    if not cur:
        return "USD"
    cur = cur.upper()
    return cur if len(cur) in (3, 4) else "USD"


def _avg_lodging_cost(accommodation: list[AccommodationOption] | None) -> float | None:
    if not accommodation:
        return None
    prices = [opt.price_per_night for opt in accommodation if opt.price_per_night is not None]
    return sum(prices) / len(prices) if prices else None


async def estimate_budget(req: BudgetRequest, itinerary: list[dict] | None = None) -> BudgetResponse:
    """
    Mocked budget estimator. If itinerary provided (list of DayPlan dicts), will
    infer lodging costs; otherwise uses inputs/defaults. No external APIs.
    """
    currency = _normalize_currency(req.currency)
    days = req.days or (len(itinerary) if itinerary else 1)
    nightly_budget = req.nightly_budget or 70.0
    food_per_day = req.food_per_day or 40.0
    incidentals_per_day = req.incidentals_per_day or 15.0
    travelers = max(1, req.travelers or 1)

    lodging_total = 0.0
    if itinerary:
        for day in itinerary:
            accom = day.get("accommodation") if isinstance(day, dict) else None
            avg = _avg_lodging_cost(accom) if accom else None
            lodging_total += avg if avg is not None else nightly_budget
    else:
        lodging_total = nightly_budget * days

    food_total = food_per_day * days * travelers
    incidentals_total = incidentals_per_day * days * travelers
    buffer_total = max(0.0, 0.05 * (lodging_total + food_total + incidentals_total))
    total = lodging_total + food_total + incidentals_total + buffer_total
    per_day = total / days if days else None

    breakdown = BudgetBreakdown(
        lodging_total=round(lodging_total, 2),
        food_total=round(food_total, 2),
        incidentals_total=round(incidentals_total, 2),
        buffer_total=round(buffer_total, 2),
    )
    return BudgetResponse(
        currency=currency,
        total=round(total, 2),
        per_day=round(per_day, 2) if per_day else None,
        breakdown=breakdown,
        notes="Mocked budget estimate; costs are approximate and exclude transportation to/from start.",
    )
