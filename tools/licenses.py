"""Professional / business license lookup.

  * NPI:  https://npiregistry.cms.hhs.gov/api/?version=2.1&...
  * FCC:  https://data.fcc.gov/api/license-view/licenses/getLicenses

UCC liens and state professional licenses don't have a single uniform
API; we provide a best-effort entrypoint that delegates to the federal
sources we DO have, and surfaces a clear "not_implemented_here" when no
upstream covers the requested combination. That keeps the tool honest
rather than fabricating data.
"""
from __future__ import annotations

from typing import Optional

from db.cache import get_cached, make_cache_key, set_cached
from tools._http import fetch_json, error_envelope

NPI_BASE = "https://npiregistry.cms.hhs.gov/api/"
FCC_BASE = "https://data.fcc.gov/api/license-view/licenses/getLicenses"


async def lookup_npi(
    name: Optional[str] = None,
    specialty: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 25,
    use_cache: bool = True,
) -> dict:
    """Look up healthcare providers in the NPPES NPI registry."""
    if not any([name, specialty, state]):
        return error_envelope(
            "missing_argument",
            detail="provide at least one of: name, specialty, state",
        )

    args = {"name": name, "specialty": specialty, "state": state, "limit": limit}
    cache_key = make_cache_key("lookup_npi", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    params: dict[str, str | int] = {
        "version": "2.1",
        "limit": min(max(int(limit), 1), 200),
    }
    if name:
        # NPPES distinguishes individual vs organization name; try organization
        # first since we don't know which the caller meant.
        params["organization_name"] = name
        params["use_first_name_alias"] = "True"
    if specialty:
        params["taxonomy_description"] = specialty
    if state:
        params["state"] = state.upper()

    raw = await fetch_json(NPI_BASE, params=params)
    if isinstance(raw, dict) and raw.get("success") is False:
        return raw
    results = raw.get("results", []) if isinstance(raw, dict) else []

    # If we searched by organization_name and got nothing, retry as last_name
    if not results and name:
        params.pop("organization_name", None)
        params["last_name"] = name
        raw = await fetch_json(NPI_BASE, params=params)
        if not (isinstance(raw, dict) and raw.get("success") is False):
            results = raw.get("results", []) if isinstance(raw, dict) else []

    normalized = []
    for r in results:
        basic = r.get("basic", {}) or {}
        addrs = r.get("addresses", []) or []
        primary_addr = next(
            (a for a in addrs if a.get("address_purpose") == "LOCATION"),
            addrs[0] if addrs else {},
        )
        taxonomies = r.get("taxonomies", []) or []
        primary_tax = next(
            (t for t in taxonomies if t.get("primary")), taxonomies[0] if taxonomies else {}
        )
        normalized.append(
            {
                "npi": r.get("number"),
                "name": (
                    basic.get("organization_name")
                    or " ".join(
                        x for x in [basic.get("first_name"), basic.get("last_name")] if x
                    )
                ),
                "credential": basic.get("credential"),
                "enumeration_type": r.get("enumeration_type"),
                "specialty": primary_tax.get("desc"),
                "state": primary_addr.get("state"),
                "city": primary_addr.get("city"),
                "telephone": primary_addr.get("telephone_number"),
            }
        )
    payload = {
        "success": True,
        "source": "nppes_npi",
        "count": len(normalized),
        "results": normalized,
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload


async def search_licenses(
    entity_name: str,
    license_type: Optional[str] = None,
    state: Optional[str] = None,
    use_cache: bool = True,
) -> dict:
    """Search professional / business licenses across federal sources.

    Routing logic:
      * license_type "npi"/"medical"/"healthcare" → NPPES
      * license_type "fcc"/"radio"/"wireless" → FCC license-view
      * else → try both and union

    Returns a normalized envelope with provenance per record so callers can
    understand which source matched.
    """
    if not entity_name or not entity_name.strip():
        return error_envelope("missing_argument", detail="entity_name is required")

    args = {"entity_name": entity_name, "license_type": license_type, "state": state}
    cache_key = make_cache_key("search_licenses", args)
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    aggregated: list[dict] = []
    sources_hit: list[str] = []
    lt = (license_type or "").lower()

    if lt in ("", "npi", "medical", "healthcare", "all"):
        npi_resp = await lookup_npi(name=entity_name, state=state, use_cache=False)
        if npi_resp.get("success"):
            sources_hit.append("nppes_npi")
            for r in npi_resp.get("results", [])[:25]:
                aggregated.append({**r, "license_source": "nppes_npi"})

    if lt in ("", "fcc", "radio", "wireless", "all"):
        fcc_params = {"format": "json", "searchValue": entity_name, "pageSize": "25"}
        if state:
            fcc_params["state"] = state.upper()
        fcc_raw = await fetch_json(FCC_BASE, params=fcc_params)
        if not (isinstance(fcc_raw, dict) and fcc_raw.get("success") is False):
            licenses = (
                (fcc_raw.get("Licenses", {}) or {}).get("License", [])
                if isinstance(fcc_raw, dict)
                else []
            )
            if licenses:
                sources_hit.append("fcc")
            for lic in licenses[:25]:
                aggregated.append(
                    {
                        "license_source": "fcc",
                        "callsign": lic.get("callsign"),
                        "licensee": lic.get("licName"),
                        "category": lic.get("categoryDesc"),
                        "service": lic.get("serviceDesc"),
                        "status": lic.get("statusDesc"),
                        "state": lic.get("licState"),
                        "frn": lic.get("frn"),
                        "expires": lic.get("expiredDate"),
                    }
                )

    payload = {
        "success": True,
        "source": "license_aggregator",
        "sources_hit": sources_hit,
        "count": len(aggregated),
        "results": aggregated,
        "cached": False,
    }
    set_cached(cache_key, payload)
    return payload


async def get_ucc_filings(debtor_name: str, state: str) -> dict:
    """UCC filings.

    State Secretary-of-State APIs are not uniform; many are HTML-only. We
    surface a clear ``not_implemented`` envelope rather than fabricate
    matches. (Roadmap: per-state adapters where SOS exposes a real API.)
    """
    if not debtor_name or not state:
        return error_envelope(
            "missing_argument", detail="debtor_name + state are required"
        )
    return {
        "success": False,
        "error": "not_implemented",
        "detail": (
            "UCC lien APIs are state-by-state and most state SOS systems "
            "lack public JSON endpoints. Roadmap: adapters for CA, DE, NY, "
            "TX. Use OpenCorporates filings + USASpending exclusions in the "
            "meantime."
        ),
        "debtor_name": debtor_name,
        "state": state,
        "cached": False,
    }
