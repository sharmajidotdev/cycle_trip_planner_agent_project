import random

from models.schemas import POIRequest, POIResponse, PointOfInterest


async def get_points_of_interest(req: POIRequest) -> POIResponse:
    """
    Mocked points-of-interest tool. Returns a few relevant POIs for a location/day.
    No external API calls.
    """
    categories = ["landmark", "park", "museum", "viewpoint", "food"]
    sample_names = [
        f"{req.location} Old Town",
        f"{req.location} Scenic Park",
        f"{req.location} Heritage Museum",
        f"{req.location} Overlook",
        f"{req.location} Market",
    ]
    pois = []
    for idx, name in enumerate(sample_names[:3]):
        pois.append(
            PointOfInterest(
                name=name,
                category=categories[idx % len(categories)],
                description=f"Popular spot in {req.location} for day {req.day}.",
                relevance="high" if idx == 0 else "medium",
            )
        )
    return POIResponse(day=req.day, location=req.location, pois=pois)
