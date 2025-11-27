from models.schemas import AccommodationOption, AccommodationRequest, AccommodationResponse


async def find_accommodation(req: AccommodationRequest) -> AccommodationResponse:
    """
    Accommodation lookup tool that returns plausible lodging options near a segment end point for a given day. Use this when you need hostels/hotels/BnBs along the cycling route; do not use it for booking or payment. Parameters: `location` is the target area for the overnight stop; `day` is the trip day, which may influence availability. Limitations: prices are approximate; it does not return booking links or confirm actual rooms. Outputs include option name, price, type, availability, and notes (e.g., bike storage, breakfast).
    """
    base_price = 50 + (len(req.location) % 40)
    options = [
        AccommodationOption(
            name=f"{req.location} Hostel",
            price_per_night=round(base_price + 10, 2),
            type="hostel",
            available=True,
            notes="Includes bike storage.",
        ),
        AccommodationOption(
            name=f"{req.location} BnB",
            price_per_night=round(base_price + 35, 2),
            type="bnb",
            available=True,
            notes="Breakfast included.",
        ),
        AccommodationOption(
            name=f"{req.location} Budget Inn",
            price_per_night=round(base_price, 2),
            type="motel",
            available=req.day % 2 == 0,  # alternate availability
            notes="Basic lodging; limited amenities.",
        ),
    ]
    return AccommodationResponse(
        day=req.day,
        location=req.location,
        options=options,
    )
