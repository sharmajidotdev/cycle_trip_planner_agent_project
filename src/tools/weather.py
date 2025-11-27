from models.schemas import WeatherDaily, WeatherRequest, WeatherResponse


async def get_weather(req: WeatherRequest) -> WeatherResponse:
    """
    Weather forecast tool that returns plausible conditions for a given location and day. Use this to provide day-level outlooks (conditions, highs/lows, precipitation chance) for cycling plans. Parameters: `location` sets the area to forecast; `day` is the trip day index used to vary conditions. Limitations: no hourly breakdown, and no wind/elevation-specific effects; it returns only day-level summaries. Outputs include conditions, high/low temperatures, and an estimated precipitation chance.
    """
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
