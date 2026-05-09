"""SEC EDGAR — full-text search across public-company filings.

EDGAR's full-text endpoint:
  https://efts.sec.gov/LATEST/search-index?q=...&forms=10-K&dateRange=custom&...

Filing detail JSON:
  https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=...

SEC requires a UA identifying the requester. Set
``PUBRECORDS_SEC_USER_AGENT`` (recommended) or accept the default.
"""
from __future__ import annotations

import os
from typing import Optional

from db.cache import get_cached, make_cache_key, set_cached
from tools._http import fetch_json, error_envelope

EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FILING_INDEX = "https://www.sec.gov/cgi-bin/browse-edgar"

VALID_FORMS = {
    "10-K", "10-Q", "8-K", "S-1", "S-3", "S-4", "DEF 14A",
    "20-F", "6-K", "13F-HR", "SC 13G", "SC 13D", "4", "3", "5",
}


def _sec_headers() -> dict:
    ua = os.getenv("PUBRECORDS_SEC_USER_AGENT")
    if ua:
        return {"User-Agent": ua}
    return {}


async def search_sec_filings(
    company_name: str,
    form_type: Optional[str] = None,
    date_from: Optional[str] = None,
    limit: int = 25,
    use_cache: bool = True,
) -> dict:
    """Full-text search EDGAR for filings mentioning ``company_name``.

    ``form_type`` accepts values like "10-K", "8-K", etc.
    ``date_from`` is YYYY-MM-DD; the upstream defaults to all-time.
    """
    if not company_name or not company_name.strip():
        return error_envelope("missing_argument", detail="company_name is required")

    args = {
        "company_name": company_name,
        "form_type": form_type,
        "date_from": date_from,
        "limit": limit,
    }
    cache_key = make_cache_key("search_sec_filings", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    params: dict[str, str | int] = {"q": company_name}
    if form_type:
        params["forms"] = form_type
    if date_from:
        params["dateRange"] = "custom"
        params["startdt"] = date_from
    raw = await fetch_json(EDGAR_SEARCH, params=params, headers=_sec_headers())
    if isinstance(raw, dict) and raw.get("success") is False:
        return raw

    hits = (raw.get("hits", {}) or {}).get("hits", []) if isinstance(raw, dict) else []
    normalized = []
    for h in hits[: max(1, int(limit))]:
        src = h.get("_source", {}) or {}
        accession = h.get("_id", "")
        # _id format: "0001193125-21-000001:doc.htm" — strip suffix
        accession_clean = accession.split(":", 1)[0] if accession else ""
        cik = (src.get("ciks") or [None])[0]
        normalized.append(
            {
                "accession_number": accession_clean,
                "company": (src.get("display_names") or [None])[0],
                "cik": cik,
                "form": src.get("form"),
                "filed_at": src.get("file_date"),
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                    f"{accession_clean.replace('-', '')}/{accession_clean}-index.htm"
                    if cik and accession_clean
                    else None
                ),
            }
        )
    payload = {
        "success": True,
        "source": "sec_edgar",
        "count": len(normalized),
        "results": normalized,
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload


async def get_sec_filing(accession_number: str, use_cache: bool = True) -> dict:
    """Return the index page for a specific filing.

    EDGAR doesn't expose a simple JSON endpoint per accession; we resolve to
    the canonical index URL plus a structured echo of the search-index hit.
    """
    if not accession_number or not accession_number.strip():
        return error_envelope("missing_argument", detail="accession_number required")

    args = {"accession_number": accession_number}
    cache_key = make_cache_key("get_sec_filing", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    raw = await fetch_json(
        EDGAR_SEARCH,
        params={"q": accession_number},
        headers=_sec_headers(),
    )
    if isinstance(raw, dict) and raw.get("success") is False:
        return raw
    hits = (raw.get("hits", {}) or {}).get("hits", []) if isinstance(raw, dict) else []
    if not hits:
        return error_envelope("not_found", detail=accession_number)

    src = hits[0].get("_source", {}) or {}
    cik = (src.get("ciks") or [None])[0]
    clean = accession_number.replace("-", "")
    payload = {
        "success": True,
        "source": "sec_edgar",
        "accession_number": accession_number,
        "company": (src.get("display_names") or [None])[0],
        "cik": cik,
        "form": src.get("form"),
        "filed_at": src.get("file_date"),
        "items": src.get("items"),
        "index_url": (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{clean}/"
            f"{accession_number}-index.htm"
            if cik
            else None
        ),
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload
