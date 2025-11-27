import logging
from typing import Optional

import httpx

from models.schemas import WeatherDaily, WeatherRequest, WeatherResponse
from tools.geocoding import geocode_location

logger = logging.getLogger(__name__)

WEATHER_CODE_MAP = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "heavy showers",
    82: "violent showers",
    95: "thunderstorm",
}


def _mock_weather(req: WeatherRequest) -> WeatherResponse:
    base_temp = 18 + (len(req.location) % 6)
    conditions_cycle = ["sunny", "partly cloudy", "breezy", "light rain", "overcast"]
    condition = conditions_cycle[req.day % len(conditions_cycle)]
    forecast = WeatherDaily(
        day=req.day,
        location=req.location,
        conditions=condition,
        high_c=float(base_temp + 6),
        low_c=float(base_temp - 2),
        precipitation_chance=round(0.05 * (req.day % 4), 2),
    )
    return WeatherResponse(daily=[forecast])


async def _fetch_weather(req: WeatherRequest) -> Optional[WeatherResponse]:
    geo = await geocode_location(req.location)
    if not geo:
        return None

    params = {
        "latitude": geo["lat"],
        "longitude": geo["lon"],
        "timezone": "auto",
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "weathercode",
            ]
        ),
        "forecast_days": max(req.day, 7),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        if not times:
            return None
        idx = max(0, min(req.day - 1, len(times) - 1))
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        precip_chances = daily.get("precipitation_probability_max") or []
        codes = daily.get("weathercode") or []
        if len(highs) <= idx or len(lows) <= idx or len(codes) <= idx:
            return None
        high = highs[idx]
        low = lows[idx]
        precip = precip_chances[idx] if len(precip_chances) > idx else 0
        code = codes[idx]
        if high is None or low is None or code is None:
            return None
        conditions = WEATHER_CODE_MAP.get(code, "mixed conditions")
        forecast = WeatherDaily(
            day=req.day,
            location=geo["name"],
            conditions=conditions,
            high_c=float(high),
            low_c=float(low),
            precipitation_chance=float(precip or 0) / 100,
        )
        return WeatherResponse(daily=[forecast])
    except Exception as exc:
        logger.warning("Weather lookup failed for %s: %s", req.location, exc)
        return None


async def get_weather(req: WeatherRequest) -> WeatherResponse:
    """
    Weather forecast tool that uses Open-Meteo's free API when available, and falls back to a deterministic mock otherwise.
    """
    api_result = await _fetch_weather(req)
    if api_result:
        return api_result
    return _mock_weather(req)
