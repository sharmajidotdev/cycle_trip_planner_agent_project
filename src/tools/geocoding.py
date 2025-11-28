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


class ReverseGeoResult(TypedDict, total=False):
    name: str
    admin1: Optional[str]
    country: Optional[str]
    lat: float
    lon: float


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


async def reverse_geocode(lat: float, lon: float) -> Optional[ReverseGeoResult]:
    """
    Reverse geocode coordinates to a nearby place name using Open-Meteo's free API.
    Returns None on any failure.
    """
    url = "https://geocoding-api.open-meteo.com/v1/reverse"
    params = {"latitude": lat, "longitude": lon, "count": 1, "language": "en", "format": "json"}
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
            "name": best.get("name"),
            "admin1": best.get("admin1"),
            "country": best.get("country"),
            "lat": float(best.get("latitude", lat)),
            "lon": float(best.get("longitude", lon)),
        }
    except Exception as exc:
        logger.warning("Reverse geocoding failed for (%s, %s): %s", lat, lon, exc)
        return None
