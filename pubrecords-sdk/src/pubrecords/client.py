"""PubRecords REST clients (sync + async)."""
from __future__ import annotations

from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = "https://mcp-pubrecords-production.up.railway.app"


class PubRecordsError(RuntimeError):
    """Raised on transport-level failures (4xx/5xx with no JSON envelope)."""


def _filter_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


class PubRecords:
    """Synchronous client.

    Example:
        >>> client = PubRecords(api_key="YOUR_API_KEY")
        >>> client.search_companies(name="Apple", state="CA")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    def __enter__(self) -> "PubRecords":
        return self

    def __exit__(self, *_exc: object) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, **params: Any) -> dict:
        resp = self._client.get(path, params=_filter_none(params))
        if resp.status_code >= 500:
            raise PubRecordsError(f"server error {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise PubRecordsError(f"invalid json from {path}: {exc}") from exc
        if resp.status_code in (401, 429):
            data.setdefault("status_code", resp.status_code)
        return data

    # -------------------- tools --------------------

    def usage(self) -> dict:
        return self._get("/usage")

    def health(self) -> dict:
        return self._get("/health")

    def search_companies(
        self,
        name: str,
        state: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 25,
    ) -> dict:
        return self._get(
            "/tools/search_companies",
            name=name, state=state, status=status, limit=limit,
        )

    def get_company_details(self, company_id: str, jurisdiction: str) -> dict:
        return self._get(
            "/tools/get_company_details",
            company_id=company_id, jurisdiction=jurisdiction,
        )

    def search_sec_filings(
        self,
        company_name: str,
        form_type: Optional[str] = None,
        date_from: Optional[str] = None,
        limit: int = 25,
    ) -> dict:
        return self._get(
            "/tools/search_sec_filings",
            company_name=company_name, form_type=form_type, date_from=date_from, limit=limit,
        )

    def get_sec_filing(self, accession_number: str) -> dict:
        return self._get("/tools/get_sec_filing", accession_number=accession_number)

    def search_court_cases(
        self,
        party_name: str,
        court: Optional[str] = None,
        date_from: Optional[str] = None,
        limit: int = 25,
    ) -> dict:
        return self._get(
            "/tools/search_court_cases",
            party_name=party_name, court=court, date_from=date_from, limit=limit,
        )

    def lookup_federal_spending(
        self,
        recipient_name: str,
        agency: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 25,
    ) -> dict:
        return self._get(
            "/tools/lookup_federal_spending",
            recipient_name=recipient_name, agency=agency, year=year, limit=limit,
        )

    def lookup_npi(
        self,
        name: Optional[str] = None,
        specialty: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 25,
    ) -> dict:
        return self._get(
            "/tools/lookup_npi",
            name=name, specialty=specialty, state=state, limit=limit,
        )

    def get_ucc_filings(self, debtor_name: str, state: str) -> dict:
        return self._get(
            "/tools/get_ucc_filings",
            debtor_name=debtor_name, state=state,
        )

    def verify_entity(self, name: str, state: Optional[str] = None) -> dict:
        return self._get("/tools/verify_entity", name=name, state=state)

    def search_licenses(
        self,
        entity_name: str,
        license_type: Optional[str] = None,
        state: Optional[str] = None,
    ) -> dict:
        return self._get(
            "/tools/search_licenses",
            entity_name=entity_name, license_type=license_type, state=state,
        )

    def search_grants(
        self,
        keyword: str = "",
        agency: Optional[str] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> dict:
        return self._get(
            "/tools/search_grants",
            keyword=keyword, agency=agency, amount_min=amount_min,
            amount_max=amount_max, status=status, limit=limit,
        )

    def get_grant_details(self, opportunity_id: str) -> dict:
        return self._get("/tools/get_grant_details", opportunity_id=opportunity_id)

    def search_contracts(
        self,
        keyword: str = "",
        naics_code: Optional[str] = None,
        agency: Optional[str] = None,
        set_aside: Optional[str] = None,
        limit: int = 10,
    ) -> dict:
        return self._get(
            "/tools/search_contracts",
            keyword=keyword, naics_code=naics_code, agency=agency,
            set_aside=set_aside, limit=limit,
        )

    def get_contract_details(self, notice_id: str) -> dict:
        return self._get("/tools/get_contract_details", notice_id=notice_id)

    def search_awards(
        self,
        recipient_name: Optional[str] = None,
        agency: Optional[str] = None,
        year: Optional[int] = None,
    ) -> dict:
        return self._get(
            "/tools/search_awards",
            recipient_name=recipient_name, agency=agency, year=year,
        )

    def get_agencies(self, type: str = "grants") -> dict:
        return self._get("/tools/get_agencies", type=type)

    def get_deadlines(self, days_ahead: int = 14) -> dict:
        return self._get("/tools/get_deadlines", days_ahead=days_ahead)

    def match_opportunities(
        self,
        org_description: str,
        org_type: Optional[str] = None,
        focus_areas: Optional[str] = None,
        limit: int = 10,
    ) -> dict:
        return self._get(
            "/tools/match_opportunities",
            org_description=org_description, org_type=org_type,
            focus_areas=focus_areas, limit=limit,
        )


class PubRecordsAsync:
    """Asyncio variant. Use as ``async with PubRecordsAsync() as c: ...``."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    async def __aenter__(self) -> "PubRecordsAsync":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **params: Any) -> dict:
        resp = await self._client.get(path, params=_filter_none(params))
        if resp.status_code >= 500:
            raise PubRecordsError(f"server error {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise PubRecordsError(f"invalid json from {path}: {exc}") from exc
        if resp.status_code in (401, 429):
            data.setdefault("status_code", resp.status_code)
        return data

    async def usage(self) -> dict:
        return await self._get("/usage")

    async def health(self) -> dict:
        return await self._get("/health")

    async def search_companies(self, name: str, state: Optional[str] = None,
                               status: Optional[str] = None, limit: int = 25) -> dict:
        return await self._get("/tools/search_companies",
                               name=name, state=state, status=status, limit=limit)

    async def get_company_details(self, company_id: str, jurisdiction: str) -> dict:
        return await self._get("/tools/get_company_details",
                               company_id=company_id, jurisdiction=jurisdiction)

    async def search_sec_filings(self, company_name: str, form_type: Optional[str] = None,
                                 date_from: Optional[str] = None, limit: int = 25) -> dict:
        return await self._get("/tools/search_sec_filings",
                               company_name=company_name, form_type=form_type,
                               date_from=date_from, limit=limit)

    async def get_sec_filing(self, accession_number: str) -> dict:
        return await self._get("/tools/get_sec_filing", accession_number=accession_number)

    async def search_court_cases(self, party_name: str, court: Optional[str] = None,
                                 date_from: Optional[str] = None, limit: int = 25) -> dict:
        return await self._get("/tools/search_court_cases",
                               party_name=party_name, court=court,
                               date_from=date_from, limit=limit)

    async def lookup_federal_spending(self, recipient_name: str, agency: Optional[str] = None,
                                      year: Optional[int] = None, limit: int = 25) -> dict:
        return await self._get("/tools/lookup_federal_spending",
                               recipient_name=recipient_name, agency=agency,
                               year=year, limit=limit)

    async def lookup_npi(self, name: Optional[str] = None, specialty: Optional[str] = None,
                         state: Optional[str] = None, limit: int = 25) -> dict:
        return await self._get("/tools/lookup_npi",
                               name=name, specialty=specialty, state=state, limit=limit)

    async def get_ucc_filings(self, debtor_name: str, state: str) -> dict:
        return await self._get("/tools/get_ucc_filings",
                               debtor_name=debtor_name, state=state)

    async def verify_entity(self, name: str, state: Optional[str] = None) -> dict:
        return await self._get("/tools/verify_entity", name=name, state=state)

    async def search_licenses(self, entity_name: str, license_type: Optional[str] = None,
                              state: Optional[str] = None) -> dict:
        return await self._get("/tools/search_licenses",
                               entity_name=entity_name, license_type=license_type,
                               state=state)

    async def search_grants(self, keyword: str = "", agency: Optional[str] = None,
                            amount_min: Optional[float] = None,
                            amount_max: Optional[float] = None,
                            status: Optional[str] = None, limit: int = 10) -> dict:
        return await self._get(
            "/tools/search_grants",
            keyword=keyword, agency=agency, amount_min=amount_min,
            amount_max=amount_max, status=status, limit=limit,
        )

    async def get_grant_details(self, opportunity_id: str) -> dict:
        return await self._get("/tools/get_grant_details", opportunity_id=opportunity_id)

    async def search_contracts(self, keyword: str = "", naics_code: Optional[str] = None,
                               agency: Optional[str] = None,
                               set_aside: Optional[str] = None, limit: int = 10) -> dict:
        return await self._get(
            "/tools/search_contracts",
            keyword=keyword, naics_code=naics_code, agency=agency,
            set_aside=set_aside, limit=limit,
        )

    async def get_contract_details(self, notice_id: str) -> dict:
        return await self._get("/tools/get_contract_details", notice_id=notice_id)

    async def search_awards(self, recipient_name: Optional[str] = None,
                            agency: Optional[str] = None,
                            year: Optional[int] = None) -> dict:
        return await self._get(
            "/tools/search_awards",
            recipient_name=recipient_name, agency=agency, year=year,
        )

    async def get_agencies(self, type: str = "grants") -> dict:
        return await self._get("/tools/get_agencies", type=type)

    async def get_deadlines(self, days_ahead: int = 14) -> dict:
        return await self._get("/tools/get_deadlines", days_ahead=days_ahead)

    async def match_opportunities(self, org_description: str,
                                  org_type: Optional[str] = None,
                                  focus_areas: Optional[str] = None,
                                  limit: int = 10) -> dict:
        return await self._get(
            "/tools/match_opportunities",
            org_description=org_description, org_type=org_type,
            focus_areas=focus_areas, limit=limit,
        )
