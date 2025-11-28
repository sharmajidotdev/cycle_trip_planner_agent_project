from models.schemas import VisaRequest, VisaRequirement, VisaResponse


async def check_visa_requirements(req: VisaRequest) -> VisaResponse:
    """
    Mocked visa requirement check. No external API calls.
    """
    # Simple heuristic: visa-free for many destinations, unless flagged.
    visa_free_pairs = {
        ("usa", "spain"),
        ("usa", "france"),
        ("usa", "denmark"),
        ("usa", "uk"),
        ("uk", "spain"),
        ("uk", "france"),
        ("uk", "usa"),
        ("france", "spain"),
        ("germany", "denmark"),
    }
    key = (req.nationality.lower(), req.destination_country.lower())
    if key in visa_free_pairs:
        reqd = VisaRequirement(
            required=False,
            type=None,
            notes="Visa-free entry for short stays (mocked data).",
            allowed_stay_days=90,
        )
    else:
        reqd = VisaRequirement(
            required=True,
            type="tourist",
            notes="Visa likely required; consult official consulate (mocked data).",
            allowed_stay_days=30,
        )
    return VisaResponse(
        nationality=req.nationality,
        destination_country=req.destination_country,
        requirement=reqd,
    )
