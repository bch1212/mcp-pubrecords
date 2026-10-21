"""Halverson IQ Data — one paid multi-tool MCP server.

Public records, Grants.gov opportunities, and SAM.gov federal contracts
share a single customer API key and a single bill. FastAPI serves /health,
/usage, and a REST mirror of every tool. FastMCP mounts the same functions
at /mcp.

Auth: X-API-Key header (required). Customer keys are issued per user.
POST /admin/keys and POST /billing/upgrade fail closed unless
PUBRECORDS_ADMIN_TOKEN is set and the X-Admin-Token header matches it.
SAM.gov credentials are read only from SAM_API_KEY.

Errors never raise: every tool returns a JSON envelope with success/error.

Note: deliberately NOT using ``from __future__ import annotations`` because
the official mcp SDK's tool registrar calls ``issubclass(param.annotation,
Context)``, which requires real types — not the lazy strings PEP-563 produces.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from db.cache import init_db
from db.keys import (
    check_and_increment,
    get_key_info,
    register_key,
)

# Tool implementations
from tools.companies import get_company_details, search_companies
from tools.contracts import (
    get_contract_details_impl,
    search_awards_impl,
    search_contracts_impl,
)
from tools.courts import search_court_cases
from tools.grants import (
    get_deadlines_impl,
    get_grant_details_impl,
    list_agencies,
    search_grants_impl,
)
from tools.licenses import get_ucc_filings, lookup_npi, search_licenses
from tools.matching import match_opportunities_impl
from tools.sec import get_sec_filing, search_sec_filings
from tools.spending import lookup_federal_spending
from tools.verification import verify_entity

log = logging.getLogger("halverson.server")
logging.basicConfig(level=os.getenv("PUBRECORDS_LOG_LEVEL", "INFO"))

UPGRADE_URL = "https://mcpize.com/pubrecords-mcp"

# Forward-declare so the lifespan can reach the MCP server (defined below).
_mcp_obj = None  # type: ignore[var-annotated]


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    # Customer keys are issued per user via /admin/keys. Boot does not
    # publish or seed a shared free-tier key.
    log.info("Halverson IQ Data boot complete")

    # The streamable HTTP transport needs its session manager running.
    if _mcp_obj is not None and hasattr(_mcp_obj, "session_manager"):
        try:
            async with _mcp_obj.session_manager.run():
                yield
                return
        except Exception as exc:  # pragma: no cover — fallback for bad versions
            log.warning("MCP session_manager.run() failed: %s", exc)
    yield


app = FastAPI(
    title="Halverson IQ Data",
    version="0.2.0",
    description=(
        "Paid multi-tool data server: public records, federal grants, "
        "and federal contracts. One API key, one bill."
    ),
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


def _require_admin(admin: Optional[str]) -> None:
    """Fail closed when the admin secret is missing or does not match.

    An unset, empty, or mismatched PUBRECORDS_ADMIN_TOKEN is the same
    outcome: 403. Callers cannot tell a missing deployment secret from
    a wrong header, and no default token is ever accepted.
    """
    expected = os.getenv("PUBRECORDS_ADMIN_TOKEN")
    if not expected or admin != expected:
        raise HTTPException(status_code=403, detail="forbidden")


def _split_csv(value: Optional[str]) -> Optional[list]:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return parts or None


def _auth_or_429(api_key: Optional[str]) -> dict:
    """Validate key or raise 401/429. Returns the per-call info dict."""
    allowed, info = check_and_increment(api_key)
    if not allowed:
        if info.get("error") == "rate_limit_exceeded":
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Free tier exhausted. Upgrade at {UPGRADE_URL}",
                    "upgrade_url": UPGRADE_URL,
                    "tier": info.get("tier"),
                },
            )
        raise HTTPException(
            status_code=401,
            detail={
                "error": info.get("error", "unauthorized"),
                "message": "Provide X-API-Key. Get a dev key at " + UPGRADE_URL,
            },
        )
    return info


# ---------------------------------------------------------------------------
# Health + usage
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "halverson-iq-data",
        "product": "Halverson IQ Data",
        "version": app.version,
    }


@app.get("/usage")
async def usage(x_api_key: str = Header(default="")) -> dict:
    info = get_key_info(x_api_key) if x_api_key else None
    if not info:
        raise HTTPException(status_code=401, detail="invalid_or_missing_api_key")
    return {
        "tier": info["tier"],
        "calls_today": info["call_count"],
        "daily_limit": info["daily_limit"],
        "remaining": max(0, info["daily_limit"] - info["call_count"]),
        "upgrade_url": UPGRADE_URL,
    }


# ---------------------------------------------------------------------------
# REST surface (mirrors MCP tools 1:1)
# ---------------------------------------------------------------------------


@app.get("/tools/search_companies")
async def http_search_companies(
    name: str,
    state: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 25,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await search_companies(name=name, state=state, status=status, limit=limit)


@app.get("/tools/get_company_details")
async def http_get_company_details(
    company_id: str,
    jurisdiction: str,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await get_company_details(company_id=company_id, jurisdiction=jurisdiction)


@app.get("/tools/search_sec_filings")
async def http_search_sec_filings(
    company_name: str,
    form_type: Optional[str] = None,
    date_from: Optional[str] = None,
    limit: int = 25,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await search_sec_filings(
        company_name=company_name, form_type=form_type, date_from=date_from, limit=limit
    )


@app.get("/tools/get_sec_filing")
async def http_get_sec_filing(
    accession_number: str,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await get_sec_filing(accession_number=accession_number)


@app.get("/tools/search_court_cases")
async def http_search_court_cases(
    party_name: str,
    court: Optional[str] = None,
    date_from: Optional[str] = None,
    limit: int = 25,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await search_court_cases(
        party_name=party_name, court=court, date_from=date_from, limit=limit
    )


@app.get("/tools/lookup_federal_spending")
async def http_lookup_federal_spending(
    recipient_name: str,
    agency: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 25,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await lookup_federal_spending(
        recipient_name=recipient_name, agency=agency, year=year, limit=limit
    )


@app.get("/tools/lookup_npi")
async def http_lookup_npi(
    name: Optional[str] = None,
    specialty: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 25,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await lookup_npi(name=name, specialty=specialty, state=state, limit=limit)


@app.get("/tools/get_ucc_filings")
async def http_get_ucc_filings(
    debtor_name: str,
    state: str,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await get_ucc_filings(debtor_name=debtor_name, state=state)


@app.get("/tools/verify_entity")
async def http_verify_entity(
    name: str,
    state: Optional[str] = None,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await verify_entity(name=name, state=state)


@app.get("/tools/search_licenses")
async def http_search_licenses(
    entity_name: str,
    license_type: Optional[str] = None,
    state: Optional[str] = None,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await search_licenses(
        entity_name=entity_name, license_type=license_type, state=state
    )


# ---------------------------------------------------------------------------
# Grants + federal contracts (same API key as the public-records tools)
# ---------------------------------------------------------------------------


@app.get("/tools/search_grants")
async def http_search_grants(
    keyword: str = "",
    agency: Optional[str] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    status: Optional[str] = "posted",
    limit: int = 10,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await search_grants_impl(
        keyword=keyword,
        agency=agency,
        amount_min=amount_min,
        amount_max=amount_max,
        status=status,
        limit=limit,
    )


@app.get("/tools/get_grant_details")
async def http_get_grant_details(
    opportunity_id: str,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await get_grant_details_impl(opportunity_id=opportunity_id)


@app.get("/tools/search_contracts")
async def http_search_contracts(
    keyword: str = "",
    naics_code: Optional[str] = None,
    agency: Optional[str] = None,
    set_aside: Optional[str] = None,
    limit: int = 10,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await search_contracts_impl(
        keyword=keyword,
        naics_code=naics_code,
        agency=agency,
        set_aside=set_aside,
        limit=limit,
    )


@app.get("/tools/get_contract_details")
async def http_get_contract_details(
    notice_id: str,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await get_contract_details_impl(notice_id=notice_id)


@app.get("/tools/match_opportunities")
async def http_match_opportunities(
    org_description: str,
    org_type: Optional[str] = None,
    focus_areas: Optional[str] = None,
    limit: int = 10,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await match_opportunities_impl(
        org_description=org_description,
        org_type=org_type,
        focus_areas=_split_csv(focus_areas),
        limit=limit,
    )


@app.get("/tools/get_agencies")
async def http_get_agencies(
    type: str = "grants",
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await list_agencies(opportunity_type=type)


@app.get("/tools/get_deadlines")
async def http_get_deadlines(
    days_ahead: int = 14,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await get_deadlines_impl(days_ahead=days_ahead)


@app.get("/tools/search_awards")
async def http_search_awards(
    recipient_name: Optional[str] = None,
    agency: Optional[str] = None,
    year: Optional[int] = None,
    x_api_key: str = Header(default=""),
) -> dict:
    _auth_or_429(x_api_key)
    return await search_awards_impl(
        recipient_name=recipient_name, agency=agency, year=year
    )


# ---------------------------------------------------------------------------
# Admin (key issuance — fails closed without the admin secret)
# ---------------------------------------------------------------------------


@app.post("/admin/keys")
async def admin_register_key(req: Request) -> dict:
    _require_admin(req.headers.get("X-Admin-Token"))
    body = await req.json()
    key = body.get("key")
    tier = body.get("tier", "free")
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    register_key(key=key, tier=tier)
    return {"registered": key, "tier": tier}


@app.post("/billing/upgrade")
async def billing_upgrade(req: Request) -> dict:
    """Promote one customer key to the paid tier. Same admin secret as /admin/keys."""
    _require_admin(req.headers.get("X-Admin-Token"))
    body = await req.json()
    key = body.get("key")
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    if get_key_info(key) is None:
        raise HTTPException(status_code=404, detail="unknown_key")
    register_key(key=key, tier="pro")
    return {"success": True, "tier": "pro"}


# ---------------------------------------------------------------------------
# MCP transport (mounted at /mcp)
# ---------------------------------------------------------------------------

try:
    # Prefer the official mcp SDK's FastMCP (it ships streamable_http_app /
    # sse_app for sub-app mounting). Fall back to the standalone fastmcp
    # package if the official one isn't present.
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except ImportError:
        from fastmcp import FastMCP  # type: ignore

    # Configure inner path to "/" so when we mount the sub-app at /mcp the
    # public URL is just /mcp (not /mcp/mcp).
    mcp = FastMCP("halverson-iq-data")
    try:
        mcp.settings.streamable_http_path = "/"
        mcp.settings.sse_path = "/"
    except Exception:  # pragma: no cover — older fastmcp lacks settings
        pass
    # Expose to the lifespan so it can run the session manager.
    globals()["_mcp_obj"] = mcp

    @mcp.tool(name="search_companies")
    async def mcp_search_companies(
        name: str,
        state: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 25,
    ) -> dict:
        """Search US business entities by name (OpenCorporates).

        Args:
            name: Company or trade name to search for.
            state: 2-letter US state code (e.g. 'CA') to narrow jurisdiction.
            status: Filter by current status (e.g. 'active', 'dissolved').
            limit: Max results (1-100, default 25).
        """
        return await search_companies(name=name, state=state, status=status, limit=limit)

    @mcp.tool(name="get_company_details")
    async def mcp_get_company_details(company_id: str, jurisdiction: str) -> dict:
        """Fetch officers, agent, and filing history for a known company.

        Args:
            company_id: OpenCorporates company number.
            jurisdiction: Jurisdiction code (e.g. 'us_de', 'us_ca').
        """
        return await get_company_details(company_id=company_id, jurisdiction=jurisdiction)

    @mcp.tool(name="search_sec_filings")
    async def mcp_search_sec_filings(
        company_name: str,
        form_type: Optional[str] = None,
        date_from: Optional[str] = None,
        limit: int = 25,
    ) -> dict:
        """Search SEC EDGAR full-text for filings.

        Args:
            company_name: Issuer name or keyword.
            form_type: Filing form (e.g. '10-K', '10-Q', '8-K').
            date_from: Earliest filing date (YYYY-MM-DD).
            limit: Max results (1-100, default 25).
        """
        return await search_sec_filings(
            company_name=company_name, form_type=form_type, date_from=date_from, limit=limit
        )

    @mcp.tool(name="get_sec_filing")
    async def mcp_get_sec_filing(accession_number: str) -> dict:
        """Fetch metadata + index URL for one SEC filing by accession number.

        Args:
            accession_number: EDGAR accession number (e.g. '0001193125-21-000001').
        """
        return await get_sec_filing(accession_number=accession_number)

    @mcp.tool(name="search_court_cases")
    async def mcp_search_court_cases(
        party_name: str,
        court: Optional[str] = None,
        date_from: Optional[str] = None,
        limit: int = 25,
    ) -> dict:
        """Search federal court cases via CourtListener (RECAP).

        Args:
            party_name: Plaintiff or defendant name.
            court: CourtListener court id (e.g. 'nyed', 'txsd').
            date_from: Earliest filing date (YYYY-MM-DD).
            limit: Max results (1-50, default 25).
        """
        return await search_court_cases(
            party_name=party_name, court=court, date_from=date_from, limit=limit
        )

    @mcp.tool(name="lookup_federal_spending")
    async def mcp_lookup_federal_spending(
        recipient_name: str,
        agency: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 25,
    ) -> dict:
        """Search USASpending.gov for awards (contracts + grants).

        Args:
            recipient_name: Award recipient name.
            agency: Awarding agency name (e.g. 'Department of Defense').
            year: Fiscal year (e.g. 2024).
            limit: Max results (1-100, default 25).
        """
        return await lookup_federal_spending(
            recipient_name=recipient_name, agency=agency, year=year, limit=limit
        )

    @mcp.tool(name="lookup_npi")
    async def mcp_lookup_npi(
        name: Optional[str] = None,
        specialty: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 25,
    ) -> dict:
        """Look up healthcare providers in the NPPES NPI registry.

        Args:
            name: Provider individual or organization name.
            specialty: Taxonomy description (e.g. 'Internal Medicine').
            state: 2-letter state code.
            limit: Max results (1-200, default 25).
        """
        return await lookup_npi(name=name, specialty=specialty, state=state, limit=limit)

    @mcp.tool(name="get_ucc_filings")
    async def mcp_get_ucc_filings(debtor_name: str, state: str) -> dict:
        """UCC lien lookup. (Roadmap; returns not_implemented per state.)

        Args:
            debtor_name: Name of the debtor.
            state: 2-letter state code.
        """
        return await get_ucc_filings(debtor_name=debtor_name, state=state)

    @mcp.tool(name="verify_entity")
    async def mcp_verify_entity(name: str, state: Optional[str] = None) -> dict:
        """Cross-reference an entity across multiple sources and score confidence.

        Args:
            name: Entity name to verify.
            state: Optional 2-letter state code for jurisdiction filtering.
        """
        return await verify_entity(name=name, state=state)

    @mcp.tool(name="search_licenses")
    async def mcp_search_licenses(
        entity_name: str,
        license_type: Optional[str] = None,
        state: Optional[str] = None,
    ) -> dict:
        """Search professional / business licenses (NPI + FCC, more sources roadmap).

        Args:
            entity_name: Licensee name.
            license_type: 'npi' | 'medical' | 'fcc' | 'radio' | 'all'.
            state: 2-letter state code.
        """
        return await search_licenses(
            entity_name=entity_name, license_type=license_type, state=state
        )

    @mcp.tool(name="search_grants")
    async def mcp_search_grants(
        keyword: str = "",
        agency: Optional[str] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        status: Optional[str] = "posted",
        limit: int = 10,
    ) -> dict:
        """Search Grants.gov funding opportunities.

        Args:
            keyword: Free-text search term.
            agency: Agency code filter (e.g. 'USDA').
            amount_min: Minimum award ceiling in USD.
            amount_max: Maximum award ceiling in USD.
            status: 'posted', 'forecasted', or 'closed'.
            limit: Max rows (1-100, default 10).
        """
        return await search_grants_impl(
            keyword=keyword,
            agency=agency,
            amount_min=amount_min,
            amount_max=amount_max,
            status=status,
            limit=limit,
        )

    @mcp.tool(name="get_grant_details")
    async def mcp_get_grant_details(opportunity_id: str) -> dict:
        """Fetch one Grants.gov opportunity by id.

        Args:
            opportunity_id: Grants.gov opportunity id.
        """
        return await get_grant_details_impl(opportunity_id=opportunity_id)

    @mcp.tool(name="search_contracts")
    async def mcp_search_contracts(
        keyword: str = "",
        naics_code: Optional[str] = None,
        agency: Optional[str] = None,
        set_aside: Optional[str] = None,
        limit: int = 10,
    ) -> dict:
        """Search SAM.gov federal contract opportunities.

        Requires SAM_API_KEY in the server environment.

        Args:
            keyword: Free-text search term.
            naics_code: NAICS industry code.
            agency: Awarding organization name.
            set_aside: SAM type-of-set-aside code (e.g. 'SBA').
            limit: Max rows (1-100, default 10).
        """
        return await search_contracts_impl(
            keyword=keyword,
            naics_code=naics_code,
            agency=agency,
            set_aside=set_aside,
            limit=limit,
        )

    @mcp.tool(name="get_contract_details")
    async def mcp_get_contract_details(notice_id: str) -> dict:
        """Fetch one SAM.gov contract notice.

        Args:
            notice_id: SAM.gov notice id.
        """
        return await get_contract_details_impl(notice_id=notice_id)

    @mcp.tool(name="match_opportunities")
    async def mcp_match_opportunities(
        org_description: str,
        org_type: Optional[str] = None,
        focus_areas: Optional[list] = None,
        limit: int = 10,
    ) -> dict:
        """Rank open grants and contracts against an organization profile.

        Args:
            org_description: What the organization does.
            org_type: Optional organization type (e.g. 'nonprofit').
            focus_areas: Keywords to match against titles and agencies.
            limit: Max matched rows (default 10).
        """
        return await match_opportunities_impl(
            org_description=org_description,
            org_type=org_type,
            focus_areas=focus_areas,
            limit=limit,
        )

    @mcp.tool(name="get_agencies")
    async def mcp_get_agencies(type: str = "grants") -> dict:
        """List agencies with open grants, contracts, or both.

        Args:
            type: 'grants', 'contracts', or 'both'.
        """
        return await list_agencies(opportunity_type=type)

    @mcp.tool(name="get_deadlines")
    async def mcp_get_deadlines(days_ahead: int = 14) -> dict:
        """Return grants closing within ``days_ahead`` days.

        Args:
            days_ahead: Lookahead window in days (default 14).
        """
        return await get_deadlines_impl(days_ahead=days_ahead)

    @mcp.tool(name="search_awards")
    async def mcp_search_awards(
        recipient_name: Optional[str] = None,
        agency: Optional[str] = None,
        year: Optional[int] = None,
    ) -> dict:
        """Search SAM.gov award notices.

        Args:
            recipient_name: Awardee name query.
            agency: Awarding organization name.
            year: Calendar year (e.g. 2025).
        """
        return await search_awards_impl(
            recipient_name=recipient_name, agency=agency, year=year
        )

    # Mount the MCP transport at /mcp (Claude can connect here).
    # Different fastmcp versions expose different app builders, so we try
    # the modern method first and fall back to SSE for older releases.
    _mounted = False
    for _factory in ("streamable_http_app", "http_app", "sse_app"):
        _maker = getattr(mcp, _factory, None)
        if _maker is None:
            continue
        try:
            app.mount("/mcp", _maker())
            log.info("MCP transport mounted via mcp.%s()", _factory)
            _mounted = True
            break
        except Exception as exc:  # pragma: no cover — version differences
            log.warning("mcp.%s() mount failed: %s", _factory, exc)
    if not _mounted:
        log.warning("No MCP transport mounted — REST surface still available")

except ImportError:  # pragma: no cover — fastmcp optional in test envs
    log.warning("fastmcp not installed; MCP transport disabled (REST still works)")


# ---------------------------------------------------------------------------
# Generic exception handler — never crash
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
    log.exception("unhandled error in %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "internal_error",
            "detail": str(exc)[:300],
        },
    )
