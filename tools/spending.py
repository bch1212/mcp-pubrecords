"""USASpending.gov — federal contracts and grant awards.

The /api/v2/search/spending_by_award/ endpoint returns awards filtered by
recipient name, awarding agency, and time period.
"""
from __future__ import annotations

from typing import Optional

from db.cache import get_cached, make_cache_key, set_cached
from tools._http import fetch_json, error_envelope

USA_SPENDING_BASE = "https://api.usaspending.gov/api/v2"


async def lookup_federal_spending(
    recipient_name: str,
    agency: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 25,
    use_cache: bool = True,
) -> dict:
    """Search USASpending for awards to ``recipient_name``."""
    if not recipient_name or not recipient_name.strip():
        return error_envelope("missing_argument", detail="recipient_name is required")

    args = {
        "recipient_name": recipient_name,
        "agency": agency,
        "year": year,
        "limit": limit,
    }
    cache_key = make_cache_key("lookup_federal_spending", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    # Build the time_period — default to a wide window if no year given
    if year:
        time_period = [{"start_date": f"{year}-01-01", "end_date": f"{year}-12-31"}]
    else:
        time_period = [{"start_date": "2008-10-01", "end_date": "2030-09-30"}]

    filters: dict = {
        "recipient_search_text": [recipient_name],
        "time_period": time_period,
        "award_type_codes": ["A", "B", "C", "D", "02", "03", "04", "05"],
    }
    if agency:
        filters["agencies"] = [
            {"type": "awarding", "tier": "toptier", "name": agency}
        ]

    body = {
        "filters": filters,
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Award Type",
            "Start Date",
            "End Date",
            "Description",
        ],
        "page": 1,
        "limit": min(max(int(limit), 1), 100),
        "sort": "Award Amount",
        "order": "desc",
    }

    raw = await fetch_json(
        f"{USA_SPENDING_BASE}/search/spending_by_award/",
        method="POST",
        json_body=body,
    )
    if isinstance(raw, dict) and raw.get("success") is False:
        return raw

    results = raw.get("results", []) if isinstance(raw, dict) else []
    normalized = [
        {
            "award_id": r.get("Award ID"),
            "recipient": r.get("Recipient Name"),
            "amount": r.get("Award Amount"),
            "awarding_agency": r.get("Awarding Agency"),
            "sub_agency": r.get("Awarding Sub Agency"),
            "award_type": r.get("Award Type"),
            "start_date": r.get("Start Date"),
            "end_date": r.get("End Date"),
            "description": r.get("Description"),
        }
        for r in results
    ]
    payload = {
        "success": True,
        "source": "usa_spending",
        "count": len(normalized),
        "total_amount": sum(
            (r.get("amount") or 0) for r in normalized if isinstance(r.get("amount"), (int, float))
        ),
        "results": normalized,
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload
