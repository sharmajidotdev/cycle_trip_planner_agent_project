from models.schemas import AccommodationOption, AccommodationRequest, AccommodationResponse


async def find_accommodation(req: AccommodationRequest) -> AccommodationResponse:
    """
    Mock accommodation lookup near a route segment end point.
    """
    options = [
        AccommodationOption(
            name="Riverside Hostel",
            price_per_night=75.0,
            type="hostel",
            available=True,
            notes="Bike storage included.",
        ),
        AccommodationOption(
            name="Parkview BnB",
            price_per_night=120.0,
            type="bnb",
            available=True,
            notes="Breakfast at 7am to help you start early.",
        ),
        AccommodationOption(
            name="Budget Inn",
            price_per_night=60.0,
            type="motel",
            available=False,
            notes="Fully booked on this date.",
        ),
    ]
    return AccommodationResponse(
        day=req.day,
        location=req.location,
        options=options,
    )
