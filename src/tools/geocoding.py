import logging
from typing import Optional, TypedDict

import httpx

logger = logging.getLogger(__name__)


class GeoResult(TypedDict):
    name: str
    lat: float
    lon: float
    country: Optional[str]
    timezone: Optional[str]


async def geocode_location(query: str) -> Optional[GeoResult]:
    """
    Resolve a place name to coordinates using the free Open-Meteo geocoding API.
    Returns None on any failure so callers can gracefully fall back to mocks.
    """
    if not query:
        return None
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": query, "count": 1, "language": "en", "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if not results:
            return None
        best = results[0]
        return {
            "name": best.get("name") or query,
            "lat": float(best["latitude"]),
            "lon": float(best["longitude"]),
            "country": best.get("country"),
            "timezone": best.get("timezone"),
        }
    except Exception as exc:
        logger.warning("Geocoding failed for %s: %s", query, exc)
        return None
