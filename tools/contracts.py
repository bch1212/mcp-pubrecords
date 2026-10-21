"""SAM.gov wrapper for federal contract opportunities and award notices.

The SAM.gov API key is read only from the ``SAM_API_KEY`` environment
variable. There is no baked-in fallback. When the variable is missing or
blank, every contract tool returns an error envelope and does not call
SAM.gov. Error text is scrubbed so a request URL cannot echo the key.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from db.cache import get_cached, make_cache_key, set_cached

SAM_OPPS_URL = "https://api.sam.gov/opportunities/v2/search"
DEFAULT_TIMEOUT = 25.0
_API_KEY_IN_URL = re.compile(r"(api_key=)[^&\s\"']+", re.IGNORECASE)


def sam_api_key() -> str:
    """Return the configured SAM.gov key, or an empty string when unset."""
    return os.getenv("SAM_API_KEY", "").strip()


def redact_secrets(text: str) -> str:
    """Remove the live SAM.gov key and any api_key query value from text."""
    secret = sam_api_key()
    if secret:
        text = text.replace(secret, "[redacted]")
    return _API_KEY_IN_URL.sub(r"\1[redacted]", text)


def _ok(data: Any, cached: bool = False) -> dict:
    return {"success": True, "cached": cached, "data": data}


def _err(message: str) -> dict:
    return {"success": False, "error": redact_secrets(message)}


def _missing_key() -> dict:
    return _err("SAM_API_KEY is not configured")


def _date_window(days_back: int = 90) -> tuple[str, str]:
    """SAM requires ``postedFrom`` + ``postedTo`` in MM/DD/YYYY."""
    today = datetime.now(timezone.utc)
    return (
        (today - timedelta(days=days_back)).strftime("%m/%d/%Y"),
        today.strftime("%m/%d/%Y"),
    )


def _remember(namespace: str, params: dict) -> tuple[str, Any]:
    key = make_cache_key(namespace, params)
    return key, get_cached(key)


async def search_contracts_impl(
    keyword: Optional[str] = None,
    naics_code: Optional[str] = None,
    agency: Optional[str] = None,
    set_aside: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """Search SAM.gov for active contract opportunities."""
    api_key = sam_api_key()
    if not api_key:
        return _missing_key()

    params_key = {
        "keyword": keyword,
        "naics_code": naics_code,
        "agency": agency,
        "set_aside": set_aside,
        "limit": limit,
    }
    cache_key, cached = _remember("sam_contracts", params_key)
    if cached is not None:
        return _ok(cached, cached=True)

    posted_from, posted_to = _date_window(90)
    params: dict[str, Any] = {
        "api_key": api_key,
        "limit": min(max(limit, 1), 100),
        "postedFrom": posted_from,
        "postedTo": posted_to,
    }
    if keyword:
        params["q"] = keyword
    if naics_code:
        params["ncode"] = naics_code
    if agency:
        params["organizationName"] = agency
    if set_aside:
        params["typeOfSetAside"] = set_aside

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(SAM_OPPS_URL, params=params)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        return _err(f"SAM.gov request failed: {exc!s}")
    except ValueError as exc:
        return _err(f"SAM.gov returned non-JSON response: {exc!s}")

    raw_hits = body.get("opportunitiesData") or []
    hits = []
    for hit in raw_hits[: params["limit"]]:
        hits.append(
            {
                "notice_id": hit.get("noticeId"),
                "title": hit.get("title"),
                "agency": hit.get("fullParentPathName"),
                "type": hit.get("type"),
                "set_aside": hit.get("typeOfSetAsideDescription"),
                "naics_code": hit.get("naicsCode"),
                "posted_date": hit.get("postedDate"),
                "response_deadline": hit.get("responseDeadLine"),
                "url": hit.get("uiLink"),
            }
        )

    result = {
        "count": len(hits),
        "results": hits,
        "total": body.get("totalRecords", len(hits)),
    }
    set_cached(cache_key, result)
    return _ok(result)


async def get_contract_details_impl(notice_id: str) -> dict:
    """Get full SAM.gov record for a single notice id."""
    if not notice_id:
        return _err("notice_id is required")
    api_key = sam_api_key()
    if not api_key:
        return _missing_key()

    cache_key, cached = _remember("sam_details", {"id": notice_id})
    if cached is not None:
        return _ok(cached, cached=True)

    posted_from, posted_to = _date_window(365)
    params = {
        "api_key": api_key,
        "limit": 1,
        "noticeid": notice_id,
        "postedFrom": posted_from,
        "postedTo": posted_to,
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(SAM_OPPS_URL, params=params)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        return _err(f"SAM.gov request failed: {exc!s}")
    except ValueError as exc:
        return _err(f"SAM.gov returned non-JSON response: {exc!s}")

    hits = body.get("opportunitiesData") or []
    if not hits:
        return _err(f"No SAM.gov record found for notice_id={notice_id}")

    set_cached(cache_key, hits[0])
    return _ok(hits[0])


async def search_awards_impl(
    recipient_name: Optional[str] = None,
    agency: Optional[str] = None,
    year: Optional[int] = None,
) -> dict:
    """Search past SAM contract awards.

    Uses the SAM opportunities endpoint filtered to Award Notice (``ptype=a``).
    USASpending award totals stay on ``lookup_federal_spending``.
    """
    api_key = sam_api_key()
    if not api_key:
        return _missing_key()

    cache_key, cached = _remember(
        "sam_awards",
        {"recipient": recipient_name, "agency": agency, "year": year},
    )
    if cached is not None:
        return _ok(cached, cached=True)

    if year:
        posted_from = f"01/01/{year}"
        posted_to = f"12/31/{year}"
    else:
        posted_from, posted_to = _date_window(365)

    params: dict[str, Any] = {
        "api_key": api_key,
        "limit": 25,
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "ptype": "a",  # SAM type code "a" = Award Notice
    }
    if recipient_name:
        params["q"] = recipient_name
    if agency:
        params["organizationName"] = agency

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(SAM_OPPS_URL, params=params)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        return _err(f"SAM.gov request failed: {exc!s}")
    except ValueError as exc:
        return _err(f"SAM.gov returned non-JSON response: {exc!s}")

    awards = []
    for hit in body.get("opportunitiesData") or []:
        award = hit.get("award") or {}
        awards.append(
            {
                "notice_id": hit.get("noticeId"),
                "title": hit.get("title"),
                "agency": hit.get("fullParentPathName"),
                "recipient": (award.get("awardee") or {}).get("name"),
                "amount": award.get("amount"),
                "award_date": award.get("date"),
                "url": hit.get("uiLink"),
            }
        )

    result = {"count": len(awards), "results": awards}
    set_cached(cache_key, result)
    return _ok(result)
