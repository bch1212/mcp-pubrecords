"""OpenCorporates — business entity search and detail lookup.

OpenCorporates allows ~50 anonymous calls/month. Set OPENCORPORATES_TOKEN
to raise the cap. Responses are normalized into ``{success, source, count,
results}`` so the MCP layer never has to inspect raw upstream shape.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from db.cache import get_cached, make_cache_key, set_cached
from tools._http import fetch_json, error_envelope

OC_BASE = "https://api.opencorporates.com/v0.4"


def _auth_params() -> dict:
    token = os.getenv("OPENCORPORATES_TOKEN")
    return {"api_token": token} if token else {}


async def search_companies(
    name: str,
    state: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 25,
    use_cache: bool = True,
) -> dict:
    """Search OpenCorporates for entities by name (optionally filtered by US state)."""
    if not name or not name.strip():
        return error_envelope("missing_argument", detail="name is required")

    args = {"name": name, "state": state, "status": status, "limit": limit}
    cache_key = make_cache_key("search_companies", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    params: dict[str, Any] = {
        "q": name,
        "per_page": min(max(int(limit), 1), 100),
        **_auth_params(),
    }
    if state:
        # OpenCorporates uses jurisdiction codes like "us_ca"
        params["jurisdiction_code"] = (
            state if state.startswith("us_") else f"us_{state.lower()}"
        )
    if status:
        params["current_status"] = status

    raw = await fetch_json(f"{OC_BASE}/companies/search", params=params)
    if isinstance(raw, dict) and raw.get("success") is False:
        return raw

    results = (
        raw.get("results", {}).get("companies", [])
        if isinstance(raw, dict)
        else []
    )
    normalized = [_normalize_company(c.get("company", {})) for c in results]
    payload = {
        "success": True,
        "source": "opencorporates",
        "count": len(normalized),
        "results": normalized,
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload


async def get_company_details(
    company_id: str, jurisdiction: str, use_cache: bool = True
) -> dict:
    """Fetch full company record (officers, agent, filings) from OpenCorporates."""
    if not company_id or not jurisdiction:
        return error_envelope(
            "missing_argument", detail="company_id + jurisdiction required"
        )

    juris = jurisdiction if jurisdiction.startswith("us_") else f"us_{jurisdiction.lower()}"
    args = {"company_id": company_id, "jurisdiction": juris}
    cache_key = make_cache_key("get_company_details", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    url = f"{OC_BASE}/companies/{juris}/{company_id}"
    raw = await fetch_json(url, params=_auth_params())
    if isinstance(raw, dict) and raw.get("success") is False:
        return raw

    company = raw.get("results", {}).get("company", {}) if isinstance(raw, dict) else {}
    if not company:
        return error_envelope("not_found", detail=f"{juris}/{company_id}")

    payload = {
        "success": True,
        "source": "opencorporates",
        "company": _normalize_company(company),
        "officers": [
            {
                "name": (o.get("officer") or {}).get("name"),
                "position": (o.get("officer") or {}).get("position"),
                "start_date": (o.get("officer") or {}).get("start_date"),
                "end_date": (o.get("officer") or {}).get("end_date"),
            }
            for o in company.get("officers", [])
        ],
        "registered_agent": company.get("registered_agent_name"),
        "filings": [
            {
                "title": (f.get("filing") or {}).get("title"),
                "date": (f.get("filing") or {}).get("date"),
                "filing_type": (f.get("filing") or {}).get("filing_type"),
            }
            for f in company.get("filings", [])
        ],
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload


def _normalize_company(c: dict) -> dict:
    if not isinstance(c, dict):
        return {}
    return {
        "name": c.get("name"),
        "company_number": c.get("company_number"),
        "jurisdiction_code": c.get("jurisdiction_code"),
        "incorporation_date": c.get("incorporation_date"),
        "dissolution_date": c.get("dissolution_date"),
        "company_type": c.get("company_type"),
        "current_status": c.get("current_status"),
        "registered_address": (
            c.get("registered_address_in_full") or c.get("registered_address")
        ),
        "opencorporates_url": c.get("opencorporates_url"),
    }
