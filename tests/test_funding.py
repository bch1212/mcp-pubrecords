"""Grants.gov and SAM.gov tools on the shared Halverson IQ Data server.

Upstream HTTP is mocked with respx. Customer auth and admin gating use the
same key store as the public-records tools.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from tools.contracts import (
    SAM_OPPS_URL,
    get_contract_details_impl,
    redact_secrets,
    sam_api_key,
    search_awards_impl,
    search_contracts_impl,
)
from tools.grants import (
    GRANTS_DETAILS_URL,
    GRANTS_SEARCH_URL,
    get_agencies_impl,
    get_deadlines_impl,
    get_grant_details_impl,
    list_agencies,
    search_grants_impl,
)
from tools.matching import match_opportunities_impl


def _grants_search_payload(rows=None):
    return {
        "oppHits": rows
        or [
            {
                "id": "12345",
                "number": "USDA-001",
                "title": "Rural broadband expansion",
                "agency": "USDA",
                "agencyCode": "USDA",
                "oppStatus": "posted",
                "openDate": "01/05/2026",
                "closeDate": "06/30/2026",
                "awardCeiling": "500000",
                "awardFloor": "10000",
            },
            {
                "id": "67890",
                "number": "DOE-002",
                "title": "Clean energy storage R&D",
                "agency": "Department of Energy",
                "agencyCode": "DOE",
                "oppStatus": "posted",
                "openDate": "02/10/2026",
                "closeDate": "05/15/2026",
                "awardCeiling": "2000000",
                "awardFloor": "100000",
            },
        ],
    }


def _sam_search_payload(rows=None):
    return {
        "totalRecords": 2,
        "opportunitiesData": rows
        or [
            {
                "noticeId": "abc123",
                "title": "Cybersecurity assessment services",
                "fullParentPathName": "DEPT OF DEFENSE",
                "type": "Solicitation",
                "typeOfSetAsideDescription": "Total Small Business",
                "naicsCode": "541512",
                "postedDate": "2026-04-01",
                "responseDeadLine": "2026-06-01T17:00:00-04:00",
                "uiLink": "https://sam.gov/opp/abc123/view",
            },
            {
                "noticeId": "def456",
                "title": "Cloud migration consulting",
                "fullParentPathName": "DEPT OF VETERANS AFFAIRS",
                "type": "Solicitation",
                "typeOfSetAsideDescription": "8(a) Set-Aside",
                "naicsCode": "541512",
                "postedDate": "2026-04-10",
                "responseDeadLine": "2026-05-20T17:00:00-04:00",
                "uiLink": "https://sam.gov/opp/def456/view",
            },
        ],
    }


# --- Grants.gov -------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_search_grants_basic_and_caches():
    route = respx.post(GRANTS_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_grants_search_payload())
    )
    first = await search_grants_impl(keyword="energy", limit=5)
    assert first["success"] is True
    assert first["cached"] is False
    assert first["data"]["count"] == 2
    assert first["data"]["results"][0]["title"].startswith("Rural broadband")

    second = await search_grants_impl(keyword="energy", limit=5)
    assert second["cached"] is True
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_search_grants_amount_filter():
    respx.post(GRANTS_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_grants_search_payload())
    )
    resp = await search_grants_impl(keyword="x", amount_min=1_000_000)
    assert resp["success"] is True
    titles = [r["title"] for r in resp["data"]["results"]]
    assert "Clean energy storage R&D" in titles
    assert "Rural broadband expansion" not in titles


@pytest.mark.asyncio
@respx.mock
async def test_search_grants_handles_upstream_5xx():
    respx.post(GRANTS_SEARCH_URL).mock(return_value=httpx.Response(503, text="boom"))
    resp = await search_grants_impl(keyword="x")
    assert resp["success"] is False
    assert "Grants.gov" in resp["error"]


@pytest.mark.asyncio
async def test_get_grant_details_required_arg():
    resp = await get_grant_details_impl(opportunity_id="")
    assert resp["success"] is False


@pytest.mark.asyncio
@respx.mock
async def test_get_grant_details_happy_path():
    respx.post(GRANTS_DETAILS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"opportunityId": "12345", "title": "Rural broadband", "synopsis": "..."},
        )
    )
    resp = await get_grant_details_impl(opportunity_id="12345")
    assert resp["success"] is True
    assert resp["data"]["title"] == "Rural broadband"


@pytest.mark.asyncio
@respx.mock
async def test_get_agencies_aggregates_and_sorts():
    respx.post(GRANTS_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json=_grants_search_payload(
                rows=[
                    {"id": "1", "title": "a", "agency": "USDA"},
                    {"id": "2", "title": "b", "agency": "USDA"},
                    {"id": "3", "title": "c", "agency": "DOE"},
                ]
            ),
        )
    )
    resp = await get_agencies_impl(type="grants")
    assert resp["success"] is True
    top = resp["data"][0]
    assert top["agency"] == "USDA"
    assert top["open_opportunities"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_deadlines_filters_window():
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%m/%d/%Y")
    far = (datetime.now(timezone.utc) + timedelta(days=120)).strftime("%m/%d/%Y")
    respx.post(GRANTS_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json=_grants_search_payload(
                rows=[
                    {"id": "1", "title": "soon", "agency": "X", "closeDate": soon},
                    {"id": "2", "title": "later", "agency": "Y", "closeDate": far},
                ]
            ),
        )
    )
    resp = await get_deadlines_impl(days_ahead=14)
    assert resp["success"] is True
    titles = [r["title"] for r in resp["data"]]
    assert titles == ["soon"]


# --- SAM.gov ----------------------------------------------------------------


def test_production_boot_does_not_seed_a_shared_key():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    assert "seed_default_keys" not in source


def test_public_docs_do_not_publish_keys():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    sdk_readme = (root / "pubrecords-sdk" / "README.md").read_text(encoding="utf-8")
    for text in (readme, sdk_readme):
        assert "pubrecords-dev-key" not in text
        assert "grantiq-dev-key" not in text
        assert "YOUR_API_KEY" in text
        assert "SAM-" not in text
    assert "SAM_API_KEY=" in env_example
    assert "PUBRECORDS_ADMIN_TOKEN=" in env_example
    for line in env_example.splitlines():
        if line.startswith("SAM_API_KEY="):
            assert line.split("=", 1)[1].strip() == ""
        if line.startswith("PUBRECORDS_ADMIN_TOKEN="):
            assert line.split("=", 1)[1].strip() == ""


def test_sam_key_is_read_from_env():
    assert sam_api_key() == "test-sam-key"


def test_sam_errors_redact_the_configured_key():
    leaked = (
        "SAM.gov request failed: "
        "https://api.sam.gov/opportunities/v2/search?api_key=test-sam-key&limit=1"
    )
    cleaned = redact_secrets(leaked)
    assert "test-sam-key" not in cleaned
    assert "api_key=[redacted]" in cleaned


def test_contracts_module_has_no_hardcoded_key_fallback():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "tools" / "contracts.py").read_text(
        encoding="utf-8"
    )
    assert "DEFAULT_API_KEY" not in source
    assert 'os.getenv("SAM_API_KEY"' in source


@pytest.mark.asyncio
@respx.mock
async def test_search_contracts_basic():
    respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json=_sam_search_payload())
    )
    resp = await search_contracts_impl(keyword="cyber", limit=5)
    assert resp["success"] is True
    assert resp["data"]["count"] == 2
    assert resp["data"]["results"][0]["notice_id"] == "abc123"


@pytest.mark.asyncio
@respx.mock
async def test_search_contracts_sends_only_the_env_key():
    route = respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json=_sam_search_payload())
    )
    resp = await search_contracts_impl(keyword="env-key-check", limit=3)
    assert resp["success"] is True
    sent = route.calls[0].request.url.params["api_key"]
    assert sent == "test-sam-key"


@pytest.mark.asyncio
@respx.mock
async def test_search_contracts_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    route = respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json=_sam_search_payload())
    )
    resp = await search_contracts_impl(keyword="should-not-call")
    assert resp["success"] is False
    assert resp["error"] == "SAM_API_KEY is not configured"
    assert route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_blank_sam_key_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("SAM_API_KEY", "   ")
    route = respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json={"opportunitiesData": []})
    )
    resp = await get_contract_details_impl(notice_id="abc123")
    assert resp["success"] is False
    assert "SAM_API_KEY" in resp["error"]
    assert route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_get_contract_details_not_found():
    respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json={"opportunitiesData": []})
    )
    resp = await get_contract_details_impl(notice_id="missing-id")
    assert resp["success"] is False
    assert "missing-id" in resp["error"]


@pytest.mark.asyncio
@respx.mock
async def test_search_awards_runs():
    respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "opportunitiesData": [
                    {
                        "noticeId": "AW-1",
                        "title": "IT services contract",
                        "fullParentPathName": "GSA",
                        "uiLink": "https://sam.gov/opp/AW-1/view",
                        "award": {
                            "awardee": {"name": "Acme Corp"},
                            "amount": "1500000",
                            "date": "2025-09-30",
                        },
                    }
                ]
            },
        )
    )
    resp = await search_awards_impl(recipient_name="Acme", year=2025)
    assert resp["success"] is True
    assert resp["data"]["results"][0]["recipient"] == "Acme Corp"


# --- Matcher ----------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_match_opportunities_orders_by_score():
    respx.post(GRANTS_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_grants_search_payload())
    )
    respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json=_sam_search_payload())
    )
    resp = await match_opportunities_impl(
        org_description="renewable energy storage startup",
        org_type="for-profit",
        focus_areas=["energy", "battery", "storage"],
    )
    assert resp["success"] is True
    results = resp["data"]["results"]
    assert results, "matcher returned no results"
    scores = [r["match_score"] for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_match_opportunities_requires_description():
    resp = await match_opportunities_impl(org_description="  ")
    assert resp["success"] is False


# --- HTTP auth + admin fail-closed ------------------------------------------


def test_funding_routes_require_api_key(client):
    r = client.get("/tools/search_grants", params={"keyword": "energy"})
    assert r.status_code == 401
    r = client.get("/tools/search_contracts", params={"keyword": "cyber"})
    assert r.status_code == 401


@respx.mock
def test_rest_search_grants_with_customer_key(client, headers):
    respx.post(GRANTS_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_grants_search_payload())
    )
    r = client.get(
        "/tools/search_grants",
        params={"keyword": "rest-energy", "limit": 2},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["count"] == 2


@respx.mock
def test_rest_search_contracts_with_customer_key(client, headers):
    respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json=_sam_search_payload())
    )
    r = client.get(
        "/tools/search_contracts",
        params={"keyword": "rest-cyber", "limit": 5},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["results"][0]["notice_id"] == "abc123"


@respx.mock
def test_rest_match_splits_focus_areas(client, headers):
    respx.post(GRANTS_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_grants_search_payload())
    )
    respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json=_sam_search_payload())
    )
    r = client.get(
        "/tools/match_opportunities",
        params={
            "org_description": "renewable energy storage startup",
            "focus_areas": "energy, battery",
        },
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["input"]["focus_areas"] == ["energy", "battery"]


@respx.mock
def test_rest_get_agencies_contracts(client, headers):
    respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json=_sam_search_payload())
    )
    r = client.get(
        "/tools/get_agencies",
        params={"type": "contracts"},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"][0]["agency"] == "DEPT OF DEFENSE"


def test_admin_fails_closed_when_secret_missing(client, monkeypatch):
    monkeypatch.delenv("PUBRECORDS_ADMIN_TOKEN", raising=False)
    r = client.post(
        "/admin/keys",
        json={"key": "customer-1", "tier": "free"},
        headers={"X-Admin-Token": "anything"},
    )
    assert r.status_code == 403


def test_admin_fails_closed_on_blank_secret(client, monkeypatch):
    monkeypatch.setenv("PUBRECORDS_ADMIN_TOKEN", "")
    r = client.post(
        "/admin/keys",
        json={"key": "customer-1", "tier": "free"},
        headers={"X-Admin-Token": "anything"},
    )
    assert r.status_code == 403


def test_admin_rejects_bad_token(client, monkeypatch):
    monkeypatch.setenv("PUBRECORDS_ADMIN_TOKEN", "test-admin-token")
    r = client.post(
        "/admin/keys",
        json={"key": "customer-1", "tier": "pro"},
        headers={"X-Admin-Token": "wrong"},
    )
    assert r.status_code == 403


def test_admin_registers_key_when_token_matches(client, monkeypatch):
    monkeypatch.setenv("PUBRECORDS_ADMIN_TOKEN", "test-admin-token")
    r = client.post(
        "/admin/keys",
        json={"key": "customer-issued-key", "tier": "free"},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] == "free"
    assert body["registered"] == "customer-issued-key"

    from db.keys import check_and_increment

    allowed, meta = check_and_increment("customer-issued-key")
    assert allowed is True
    assert meta["tier"] == "free"


def test_billing_upgrade_fails_closed_and_promotes(client, monkeypatch):
    monkeypatch.delenv("PUBRECORDS_ADMIN_TOKEN", raising=False)
    blocked = client.post(
        "/billing/upgrade",
        json={"key": "customer-issued-key"},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert blocked.status_code == 403

    monkeypatch.setenv("PUBRECORDS_ADMIN_TOKEN", "test-admin-token")
    from db.keys import PRO_DAILY_LIMIT, get_key_info, register_key

    register_key("billing-customer", tier="free")
    wrong = client.post(
        "/billing/upgrade",
        json={"key": "billing-customer"},
        headers={"X-Admin-Token": "nope"},
    )
    assert wrong.status_code == 403

    promoted = client.post(
        "/billing/upgrade",
        json={"key": "billing-customer"},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["tier"] == "pro"
    assert "billing-customer" not in promoted.text
    info = get_key_info("billing-customer")
    assert info["tier"] == "pro"
    assert info["daily_limit"] == PRO_DAILY_LIMIT


@pytest.mark.asyncio
@respx.mock
async def test_list_agencies_both_merges_sources():
    respx.post(GRANTS_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json=_grants_search_payload(
                rows=[{"id": "1", "title": "a", "agency": "USDA"}]
            ),
        )
    )
    respx.get(SAM_OPPS_URL).mock(
        return_value=httpx.Response(200, json=_sam_search_payload())
    )
    resp = await list_agencies("both")
    assert resp["success"] is True
    names = {row["agency"] for row in resp["data"]}
    assert "USDA" in names
    assert "DEPT OF DEFENSE" in names
