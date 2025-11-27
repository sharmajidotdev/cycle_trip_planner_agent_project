from models.schemas import WeatherDaily, WeatherRequest, WeatherResponse


async def get_weather(req: WeatherRequest) -> WeatherResponse:
    """
    Mock weather forecast for the requested day and location.
    """
    forecast = WeatherDaily(
        day=req.day,
        location=req.location,
        conditions="sunny with light winds",
        high_c=24.0,
        low_c=15.0,
        precipitation_chance=0.1,
    )
    return WeatherResponse(daily=[forecast])
