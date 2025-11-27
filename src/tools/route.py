
import logging
import math
from typing import Optional

import httpx

from models.schemas import RouteRequest, RouteResponse
from tools.geocoding import geocode_location

logger = logging.getLogger(__name__)


async def _fetch_osrm_distance_km(start: str, end: str) -> Optional[float]:
    start_geo = await geocode_location(start)
    end_geo = await geocode_location(end)
    if not start_geo or not end_geo:
        return None

    url = f"https://router.project-osrm.org/route/v1/cycling/{start_geo['lon']},{start_geo['lat']};{end_geo['lon']},{end_geo['lat']}"
    params = {"overview": "false", "alternatives": "false", "steps": "false"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        data = resp.json()
        routes = data.get("routes") or []
        if not routes:
            return None
        distance_m = float(routes[0].get("distance", 0.0))
        distance_km = distance_m / 1000
        return distance_km if distance_km > 0 else None
    except Exception as exc:
        logger.warning("OSRM route lookup failed for %s -> %s: %s", start, end, exc)
        return None


def _build_mock_route(req: RouteRequest) -> RouteResponse:
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


async def get_route(req: RouteRequest) -> RouteResponse:
    """
    Route planning tool that first tries OSRM's free bicycle routing API, then falls back to the existing mock output on any failure.
    """
    api_distance_km = await _fetch_osrm_distance_km(req.start, req.end)
    if api_distance_km:
        daily_target = max(req.daily_distance_km, 20)
        days = max(1, math.ceil(api_distance_km / daily_target))
        remaining = api_distance_km
        segments = []
        last_point = req.start
        for day in range(1, days + 1):
            distance = min(daily_target, remaining)
            remaining -= distance
            end_point = req.end if day == days else f"Stop {day} toward {req.end}"
            note = "Based on OSRM bike routing." if day == 1 else None
            if day == days:
                note = note or "Final approach to destination."
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
            total_distance_km=round(api_distance_km, 1),
            days=days,
            segments=segments,
        )

    return _build_mock_route(req)
