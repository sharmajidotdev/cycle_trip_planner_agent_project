
from models.schemas import RouteRequest, RouteResponse

async def get_route(req: RouteRequest) -> RouteResponse:
    """
    Compute a cycling route between two points.
    For the take-home, this can be mocked with static data.
    """
    # Mocked response
    return RouteResponse(
        total_distance_km=150.0,
        days=3,
        segments=[
            {
                "day": 1,
                "distance_km": 50.0,
                "start": req.start,
                "end": "Midpoint A",
                "notes": "Scenic route along the river.",
            },
            {
                "day": 2,
                "distance_km": 50.0,
                "start": "Midpoint A",
                "end": "Midpoint B",
                "notes": None,
            },
            {
                "day": 3,
                "distance_km": 50.0,
                "start": "Midpoint B",
                "end": req.end,
                "notes": "Challenging hills towards the end.",
            },
        ],
    )
