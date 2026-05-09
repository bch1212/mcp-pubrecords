"""CourtListener — federal court case search (RECAP).

Set ``COURTLISTENER_TOKEN`` to raise the anonymous rate limit. The free
limit is sufficient for development.
"""
from __future__ import annotations

import os
from typing import Optional

from db.cache import get_cached, make_cache_key, set_cached
from tools._http import fetch_json, error_envelope

CL_BASE = "https://www.courtlistener.com/api/rest/v4"


def _cl_headers() -> dict:
    token = os.getenv("COURTLISTENER_TOKEN")
    return {"Authorization": f"Token {token}"} if token else {}


async def search_court_cases(
    party_name: str,
    court: Optional[str] = None,
    date_from: Optional[str] = None,
    limit: int = 25,
    use_cache: bool = True,
) -> dict:
    """Search RECAP for federal court cases involving ``party_name``.

    ``court`` is a CourtListener court id (e.g. "nyed", "txsd") — optional.
    ``date_from`` is YYYY-MM-DD (filed_after).
    """
    if not party_name or not party_name.strip():
        return error_envelope("missing_argument", detail="party_name is required")

    args = {
        "party_name": party_name,
        "court": court,
        "date_from": date_from,
        "limit": limit,
    }
    cache_key = make_cache_key("search_court_cases", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    params: dict[str, str | int] = {
        "type": "r",  # RECAP docket search
        "q": party_name,
        "page_size": min(max(int(limit), 1), 50),
    }
    if court:
        params["court"] = court
    if date_from:
        params["filed_after"] = date_from

    raw = await fetch_json(
        f"{CL_BASE}/search/", params=params, headers=_cl_headers()
    )
    if isinstance(raw, dict) and raw.get("success") is False:
        return raw

    results = raw.get("results", []) if isinstance(raw, dict) else []
    normalized = [
        {
            "case_name": r.get("caseName") or r.get("case_name"),
            "court": r.get("court") or r.get("court_id"),
            "docket_number": r.get("docketNumber") or r.get("docket_number"),
            "filed": r.get("dateFiled") or r.get("date_filed"),
            "nature_of_suit": r.get("suitNature") or r.get("nature_of_suit"),
            "absolute_url": (
                f"https://www.courtlistener.com{r.get('absolute_url')}"
                if r.get("absolute_url")
                else None
            ),
        }
        for r in results
    ]
    payload = {
        "success": True,
        "source": "courtlistener",
        "count": len(normalized),
        "results": normalized,
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload
