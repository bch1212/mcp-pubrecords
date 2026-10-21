"""Grants.gov wrapper.

Grants.gov exposes a free, public REST API for federal grant
opportunities. Listings come from ``/grantsws/rest/opportunities/search``
and a single record from ``/grantsws/rest/opportunity/details``.

Responses are cached in the shared Halverson IQ Data SQLite store.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from db.cache import get_cached, make_cache_key, set_cached

GRANTS_SEARCH_URL = "https://apply07.grants.gov/grantsws/rest/opportunities/search"
GRANTS_DETAILS_URL = "https://apply07.grants.gov/grantsws/rest/opportunity/details"
DEFAULT_TIMEOUT = 20.0


def _ok(data: Any, cached: bool = False) -> dict:
    return {"success": True, "cached": cached, "data": data}


def _err(message: str) -> dict:
    return {"success": False, "error": message}


def _remember(namespace: str, params: dict) -> tuple[str, Any]:
    key = make_cache_key(namespace, params)
    return key, get_cached(key)


async def search_grants_impl(
    keyword: Optional[str] = None,
    agency: Optional[str] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    status: Optional[str] = "posted",
    limit: int = 10,
) -> dict:
    """Search Grants.gov by keyword + filters."""
    params = {
        "keyword": keyword,
        "agency": agency,
        "amount_min": amount_min,
        "amount_max": amount_max,
        "status": status,
        "limit": limit,
    }
    cache_key, cached = _remember("grants_search", params)
    if cached is not None:
        return _ok(cached, cached=True)

    payload = {
        "keyword": keyword or "",
        "oppNum": "",
        "cfda": "",
        "agencies": agency or "",
        "fundingCategories": "",
        "fundingInstruments": "",
        "eligibilities": "",
        "rows": min(max(limit, 1), 100),
        "oppStatuses": (status or "posted").lower(),
        "sortBy": "openDate|desc",
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(GRANTS_SEARCH_URL, json=payload)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        return _err(f"Grants.gov request failed: {exc!s}")
    except ValueError as exc:
        return _err(f"Grants.gov returned non-JSON response: {exc!s}")

    raw_hits = body.get("oppHits") or []
    hits = []
    for hit in raw_hits[: payload["rows"]]:
        award_min = hit.get("awardCeiling") or hit.get("awardFloor")
        try:
            award_value = float(award_min) if award_min not in (None, "") else None
        except (TypeError, ValueError):
            award_value = None
        # Apply server-side amount filters (the upstream API does not honor them).
        if amount_min is not None and (award_value or 0) < amount_min:
            continue
        if amount_max is not None and (award_value or 0) > amount_max:
            continue
        hits.append(
            {
                "opportunity_id": hit.get("id") or hit.get("opportunityId"),
                "opportunity_number": hit.get("number") or hit.get("oppNumber"),
                "title": hit.get("title"),
                "agency": hit.get("agency") or hit.get("agencyName"),
                "agency_code": hit.get("agencyCode"),
                "status": hit.get("oppStatus") or hit.get("opportunityStatus"),
                "post_date": hit.get("openDate"),
                "close_date": hit.get("closeDate"),
                "award_ceiling": hit.get("awardCeiling"),
                "award_floor": hit.get("awardFloor"),
                "url": (
                    f"https://www.grants.gov/search-results-detail/{hit.get('id')}"
                    if hit.get("id")
                    else None
                ),
            }
        )

    result = {"count": len(hits), "results": hits}
    set_cached(cache_key, result)
    return _ok(result)


async def get_grant_details_impl(opportunity_id: str) -> dict:
    """Look up a single grant by opportunity id."""
    if not opportunity_id:
        return _err("opportunity_id is required")

    cache_key, cached = _remember("grants_details", {"id": opportunity_id})
    if cached is not None:
        return _ok(cached, cached=True)

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                GRANTS_DETAILS_URL, json={"opportunityId": str(opportunity_id)}
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        return _err(f"Grants.gov request failed: {exc!s}")
    except ValueError as exc:
        return _err(f"Grants.gov returned non-JSON response: {exc!s}")

    set_cached(cache_key, body)
    return _ok(body)


async def get_agencies_impl(type: str = "grants") -> dict:
    """Aggregate distinct agency names from a wide search.

    Grants.gov has no public "list all agencies" endpoint, so we sample
    the latest 100 postings and dedupe their agency names.
    """
    cache_key, cached = _remember("grants_agencies", {"type": type})
    if cached is not None:
        return _ok(cached, cached=True)

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                GRANTS_SEARCH_URL,
                json={
                    "keyword": "",
                    "rows": 100,
                    "oppStatuses": "posted",
                    "sortBy": "openDate|desc",
                },
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        return _err(f"Grants.gov request failed: {exc!s}")

    agencies: dict[str, int] = {}
    for hit in body.get("oppHits") or []:
        name = hit.get("agency") or hit.get("agencyName")
        if name:
            agencies[name] = agencies.get(name, 0) + 1

    result = sorted(
        ({"agency": name, "open_opportunities": cnt} for name, cnt in agencies.items()),
        key=lambda r: r["open_opportunities"],
        reverse=True,
    )
    set_cached(cache_key, result)
    return _ok(result)


async def get_deadlines_impl(days_ahead: int = 14) -> dict:
    """Return grants whose close_date is within `days_ahead` days from now."""
    from datetime import datetime, timedelta, timezone

    cache_key, cached = _remember("grants_deadlines", {"days_ahead": days_ahead})
    if cached is not None:
        return _ok(cached, cached=True)

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                GRANTS_SEARCH_URL,
                json={
                    "keyword": "",
                    "rows": 100,
                    "oppStatuses": "posted",
                    "sortBy": "closeDate|asc",
                },
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as exc:
        return _err(f"Grants.gov request failed: {exc!s}")

    cutoff = datetime.now(timezone.utc) + timedelta(days=max(days_ahead, 1))
    soon = []
    for hit in body.get("oppHits") or []:
        raw = hit.get("closeDate")
        if not raw:
            continue
        parsed = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        if parsed is None or parsed > cutoff:
            continue
        soon.append(
            {
                "opportunity_id": hit.get("id"),
                "title": hit.get("title"),
                "agency": hit.get("agency"),
                "close_date": raw,
                "days_until_close": max((parsed - datetime.now(timezone.utc)).days, 0),
            }
        )

    soon.sort(key=lambda r: r["days_until_close"])
    set_cached(cache_key, soon)
    return _ok(soon)


async def list_agencies(opportunity_type: str = "grants") -> dict:
    """List agencies with open grants, contracts, or both.

    Contract counts come from the SAM.gov search wrapper, which reads
    ``SAM_API_KEY`` from the environment and fails closed when it is unset.
    """
    kind = (opportunity_type or "grants").strip().lower()
    if kind == "grants":
        return await get_agencies_impl(type="grants")
    if kind == "contracts":
        return await _agencies_from_contracts()
    if kind == "both":
        return await _agencies_combined()
    return _err("type must be one of: grants, contracts, both")


async def _agencies_from_contracts() -> dict:
    from tools.contracts import search_contracts_impl

    contracts = await search_contracts_impl(limit=100)
    if not contracts.get("success"):
        return contracts
    seen: dict[str, int] = {}
    for row in (contracts.get("data") or {}).get("results", []):
        name = row.get("agency")
        if name:
            seen[name] = seen.get(name, 0) + 1
    ranked = sorted(
        ({"agency": k, "open_opportunities": v} for k, v in seen.items()),
        key=lambda r: r["open_opportunities"],
        reverse=True,
    )
    return _ok(ranked)


async def _agencies_combined() -> dict:
    from tools.contracts import search_contracts_impl

    grants = await get_agencies_impl(type="grants")
    contracts = await search_contracts_impl(limit=100)
    seen: dict[str, int] = {}
    if grants.get("success"):
        for row in grants.get("data") or []:
            seen[row["agency"]] = seen.get(row["agency"], 0) + int(
                row.get("open_opportunities") or 0
            )
    if contracts.get("success"):
        for row in (contracts.get("data") or {}).get("results", []):
            name = row.get("agency")
            if name:
                seen[name] = seen.get(name, 0) + 1
    if not seen and not grants.get("success"):
        return grants
    if not seen and not contracts.get("success"):
        return contracts
    ranked = sorted(
        ({"agency": k, "open_opportunities": v} for k, v in seen.items()),
        key=lambda r: r["open_opportunities"],
        reverse=True,
    )
    return _ok(ranked)
