
import logging
import math
from typing import Optional, Tuple, List

import httpx

from models.schemas import RouteRequest, RouteResponse
from tools.geocoding import geocode_location, reverse_geocode

logger = logging.getLogger(__name__)


def _haversine_km(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    lat1, lon1 = p1
    lat2, lon2 = p2
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _fetch_osrm_route(start: str, end: str) -> Optional[dict]:
    start_geo = await geocode_location(start)
    end_geo = await geocode_location(end)
    if not start_geo or not end_geo:
        return None

    url = f"https://router.project-osrm.org/route/v1/cycling/{start_geo['lon']},{start_geo['lat']};{end_geo['lon']},{end_geo['lat']}"
    params = {"overview": "full", "geometries": "geojson", "alternatives": "false", "steps": "false"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        data = resp.json()
        routes = data.get("routes") or []
        if not routes:
            return None
        return routes[0]
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


async def _label_stops_with_towns(
    coords: List[Tuple[float, float]], target_points: List[Tuple[float, float]]
) -> List[str]:
    names: List[str] = []
    for lat, lon in target_points:
        if lat is None or lon is None:
            names.append("Unnamed stop")
            continue
        place = await reverse_geocode(lat, lon)
        if place:
            name_bits = [bit for bit in [place.get("name"), place.get("admin1"), place.get("country")] if bit]
            names.append(", ".join(name_bits))
        else:
            names.append(f"Stop near {round(lat, 2)},{round(lon, 2)}")
    return names


async def get_route(req: RouteRequest) -> RouteResponse:
    """
    Route planning tool that first tries OSRM's free bicycle routing API, then falls back to the existing mock output on any failure.
    """
    osrm_route = await _fetch_osrm_route(req.start, req.end)
    if osrm_route:
        distance_km = float(osrm_route.get("distance", 0)) / 1000
        daily_target = max(req.daily_distance_km, 20)
        days = max(1, math.ceil(distance_km / daily_target))
        coords = osrm_route.get("geometry", {}).get("coordinates") or []
        # Build cumulative distances to locate day stops along the line
        cumulative_km: List[float] = [0.0]
        for i in range(1, len(coords)):
            prev = coords[i - 1]
            cur = coords[i]
            cumulative_km.append(
                cumulative_km[-1] + _haversine_km((prev[1], prev[0]), (cur[1], cur[0]))
            )

        target_points: List[Tuple[float, float]] = []
        for day in range(1, days + 1):
            target_distance = min(day * daily_target, distance_km)
            # Find nearest point along the polyline to this target distance
            nearest_idx = min(
                range(len(cumulative_km)), key=lambda idx: abs(cumulative_km[idx] - target_distance)
            ) if cumulative_km else 0
            coord = coords[nearest_idx] if coords else [None, None]
            if coord[1] is not None and coord[0] is not None:
                target_points.append((coord[1], coord[0]))  # lat, lon
            else:
                target_points.append((None, None))

        stop_names = await _label_stops_with_towns(coords, target_points)

        segments = []
        last_point = req.start
        for day in range(1, days + 1):
            distance = daily_target if day < days else max(round(distance_km - daily_target * (days - 1), 1), 0.1)
            end_point = req.end if day == days else stop_names[day - 1] if day - 1 < len(stop_names) else f"Stop {day}"
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
            total_distance_km=round(distance_km, 1),
            days=days,
            segments=segments,
        )

    return _build_mock_route(req)
