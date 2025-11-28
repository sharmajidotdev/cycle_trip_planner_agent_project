import logging
from typing import List, Optional

import httpx

from models.schemas import AccommodationOption, AccommodationRequest, AccommodationResponse
from tools.geocoding import geocode_location

logger = logging.getLogger(__name__)


def _mock_accommodation(req: AccommodationRequest) -> AccommodationResponse:
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


async def _fetch_accommodation(req: AccommodationRequest) -> Optional[AccommodationResponse]:
    geo = await geocode_location(req.location)
    if not geo:
        return None

    # Query Overpass (OpenStreetMap) for nearby lodging points of interest.
    query = f"""
    [out:json][timeout:10];
    (
      node["tourism"~"hotel|hostel|motel|guest_house|chalet"](around:5000,{geo['lat']},{geo['lon']});
      way["tourism"~"hotel|hostel|motel|guest_house|chalet"](around:5000,{geo['lat']},{geo['lon']});
      relation["tourism"~"hotel|hostel|motel|guest_house|chalet"](around:5000,{geo['lat']},{geo['lon']});
    );
    out center 8;
    """
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get("https://overpass-api.de/api/interpreter", params={"data": query})
            resp.raise_for_status()
        data = resp.json()
        elements = data.get("elements") or []
        if not elements:
            return None

        options: List[AccommodationOption] = []
        base_price = 55 + (req.day * 5)
        for idx, element in enumerate(elements[:6]):
            tags = element.get("tags") or {}
            name = tags.get("name") or f"Option {idx + 1} near {geo['name']}"
            typ = tags.get("tourism", "bnb").replace("_", " ")
            price = round(base_price + (idx * 8), 2)
            available = (req.day + idx) % 2 == 0
            note_bits = []
            if tags.get("bicycle_parking"):
                note_bits.append("Bike parking reported nearby.")
            if tags.get("internet_access"):
                note_bits.append("Internet available.")
            if tags.get("breakfast"):
                note_bits.append("Breakfast noted.")
            note = "; ".join(note_bits) if note_bits else f"Near {geo['name']} center."
            options.append(
                AccommodationOption(
                    name=name,
                    price_per_night=price,
                    type=typ,
                    available=available,
                    notes=note,
                )
            )

        if not options:
            return None

        return AccommodationResponse(
            day=req.day,
            location=geo["name"],
            options=options,
        )
    except Exception as exc:
        logger.warning("Accommodation lookup failed for %s: %s", req.location, exc)
        return None


async def find_accommodation(req: AccommodationRequest) -> AccommodationResponse:
    """
    Accommodation lookup that tries the free Overpass (OpenStreetMap) API first, then falls back to the deterministic mock data.
    """
    api_result = await _fetch_accommodation(req)
    if api_result:
        return api_result
    return _mock_accommodation(req)
