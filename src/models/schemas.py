from pydantic import BaseModel

class RouteRequest(BaseModel):
    start: str
    end: str
    daily_distance_km: int

class RouteSegment(BaseModel):
    day: int
    distance_km: float
    start: str
    end: str
    notes: str | None = None

class RouteResponse(BaseModel):
    total_distance_km: float
    days: int
    segments: list[RouteSegment]


class AccommodationRequest(BaseModel):
    location: str
    day: int


class AccommodationOption(BaseModel):
    name: str
    price_per_night: float
    type: str
    available: bool
    notes: str | None = None


class AccommodationResponse(BaseModel):
    day: int
    location: str
    options: list[AccommodationOption]


class WeatherRequest(BaseModel):
    location: str
    day: int


class WeatherDaily(BaseModel):
    day: int
    location: str
    conditions: str
    high_c: float
    low_c: float
    precipitation_chance: float


class WeatherResponse(BaseModel):
    daily: list[WeatherDaily]
