
import math
from models.schemas import RouteRequest, RouteResponse


async def get_route(req: RouteRequest) -> RouteResponse:
    """
    Route planning tool that returns a realistic-looking multi-day cycling route based on a start location, end location, and desired daily distance. Use this when you need to break a trip into daily cycling segments with distances and brief notes; do not use it for walking, driving, or non-cycling contexts. Parameters: `start` and `end` define the trip endpoints; `daily_distance_km` sets target distance per day and influences how many days/segments are produced. Limitations: no turn-by-turn directions. It does not return elevation, surfaces, or safety constraints—only day-level segments with start/end and notes.
    """
    base_distance = 160.0 + (len(req.start) + len(req.end)) % 40  # slight variation
    days = max(1, math.ceil(base_distance / max(req.daily_distance_km, 20)))
    remaining = base_distance
    segments = []
    last_point = req.start
    for day in range(1, days + 1):
        distance = min(req.daily_distance_km, remaining)
        remaining -= distance
        end_point = f"Stop {day}" if day < days else req.end
        note = "Scenic route along secondary roads." if day == 1 else None
        if day == days:
            note = note or "Challenging hills toward the end."
        segments.append(
            {
                "day": day,
                "distance_km": round(distance, 1),
                "start": last_point,
                "end": end_point,
                "notes": note,
            }
        )
        last_point = end_point

    return RouteResponse(
        total_distance_km=round(base_distance, 1),
        days=days,
        segments=segments,
    )
