import random

from models.schemas import ElevationProfile, ElevationRequest, ElevationResponse


async def get_elevation_profile(req: ElevationRequest) -> ElevationResponse:
    """
    Get terrain difficulty — elevation gain, elevation loss, and a simple difficulty rating for a location/day.
    This is fully mocked and does not call any external APIs.
    """
    base_gain = 400 + (len(req.location) % 200)  # vary by location length
    variability = random.randint(-80, 120)
    gain = max(100, base_gain + variability)
    loss = max(50, int(gain * 0.6))
    if gain < 300:
        difficulty = "easy"
    elif gain < 600:
        difficulty = "moderate"
    else:
        difficulty = "hard"

    profile = ElevationProfile(
        day=req.day,
        location=req.location,
        elevation_gain_m=float(gain),
        elevation_loss_m=float(loss),
        difficulty=difficulty,
        notes="Mocked elevation profile; no live terrain data.",
    )
    return ElevationResponse(profile=[profile])
