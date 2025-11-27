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
