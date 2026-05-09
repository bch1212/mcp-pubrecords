"""Cross-source entity verification.

We hit OpenCorporates, EDGAR, and USASpending in parallel. Each that
returns at least one result contributes to a confidence score:
    OpenCorporates: +40
    EDGAR (SEC):    +30
    USASpending:    +30

Score is capped at 100. Any source that errors counts as 0 — never as
"verified".
"""
from __future__ import annotations

import asyncio

from db.cache import get_cached, make_cache_key, set_cached

from tools.companies import search_companies
from tools.sec import search_sec_filings
from tools.spending import lookup_federal_spending


async def verify_entity(name: str, state: str | None = None, use_cache: bool = True) -> dict:
    """Cross-reference name across multiple sources and return a confidence score."""
    if not name or not name.strip():
        return {
            "success": False,
            "error": "missing_argument",
            "detail": "name is required",
            "cached": False,
        }

    args = {"name": name, "state": state}
    cache_key = make_cache_key("verify_entity", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    corp_task = search_companies(name=name, state=state, limit=5, use_cache=use_cache)
    sec_task = search_sec_filings(company_name=name, limit=3, use_cache=use_cache)
    spend_task = lookup_federal_spending(recipient_name=name, limit=3, use_cache=use_cache)
    corp, sec, spend = await asyncio.gather(corp_task, sec_task, spend_task)

    sources: list[str] = []
    confidence = 0
    matches: dict = {}

    if corp.get("success") and corp.get("count", 0) > 0:
        sources.append("opencorporates")
        confidence += 40
        matches["opencorporates"] = corp["results"][:3]
    if sec.get("success") and sec.get("count", 0) > 0:
        sources.append("sec_edgar")
        confidence += 30
        matches["sec_edgar"] = sec["results"][:3]
    if spend.get("success") and spend.get("count", 0) > 0:
        sources.append("usa_spending")
        confidence += 30
        matches["usa_spending"] = spend["results"][:3]

    confidence = min(100, confidence)
    payload = {
        "success": True,
        "name": name,
        "state": state,
        "confidence": confidence,
        "verdict": _verdict_for(confidence),
        "sources": sources,
        "matches": matches,
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload


def _verdict_for(confidence: int) -> str:
    if confidence >= 70:
        return "high_confidence_match"
    if confidence >= 40:
        return "partial_match"
    if confidence > 0:
        return "weak_match"
    return "no_match"
