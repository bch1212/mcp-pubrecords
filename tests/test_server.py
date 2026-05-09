"""End-to-end tests for PubRecords MCP.

Network calls are stubbed via respx so the suite is offline-deterministic.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures local to this file
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    # Import after _isolated_db has set PUBRECORDS_DB_PATH
    from server import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def headers():
    return {"X-API-Key": "pubrecords-dev-key-001"}


def _ok(resp: httpx.Response) -> dict:
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Cache + key tests (no network)
# ---------------------------------------------------------------------------


def test_cache_roundtrip():
    from db.cache import get_cached, make_cache_key, set_cached

    key = make_cache_key("foo", {"a": 1})
    assert get_cached(key) is None
    set_cached(key, {"hello": "world"})
    assert get_cached(key) == {"hello": "world"}


def test_cache_key_stable():
    from db.cache import make_cache_key

    a = make_cache_key("foo", {"a": 1, "b": 2})
    b = make_cache_key("foo", {"b": 2, "a": 1})
    assert a == b, "cache key should be order-independent"


def test_api_key_seeded_and_increments():
    from db.keys import DEV_API_KEY, check_and_increment, get_key_info

    info = get_key_info(DEV_API_KEY)
    assert info is not None
    assert info["tier"] == "free"
    starting = info["call_count"]

    allowed, meta = check_and_increment(DEV_API_KEY)
    assert allowed is True
    assert meta["tier"] == "free"

    info2 = get_key_info(DEV_API_KEY)
    assert info2["call_count"] == starting + 1


def test_invalid_api_key_blocked():
    from db.keys import check_and_increment

    allowed, meta = check_and_increment("not-a-key")
    assert allowed is False
    assert meta["error"] == "invalid_api_key"


def test_rate_limit_exhaustion(monkeypatch):
    from db.keys import (
        DEV_API_KEY,
        FREE_DAILY_LIMIT,
        check_and_increment,
        get_key_info,
    )

    # Exhaust the bucket
    for _ in range(FREE_DAILY_LIMIT):
        check_and_increment(DEV_API_KEY)
    info = get_key_info(DEV_API_KEY)
    assert info["call_count"] == FREE_DAILY_LIMIT
    allowed, meta = check_and_increment(DEV_API_KEY)
    assert allowed is False
    assert meta["error"] == "rate_limit_exceeded"
    assert "upgrade_url" in meta


# ---------------------------------------------------------------------------
# HTTP / FastAPI surface
# ---------------------------------------------------------------------------


def test_health_no_auth_required(client):
    r = client.get("/health")
    body = _ok(r)
    assert body["status"] == "ok"
    assert body["service"] == "pubrecords-mcp"


def test_missing_api_key_rejected(client):
    r = client.get("/tools/search_companies", params={"name": "Acme"})
    assert r.status_code == 401


def test_search_companies_happy_path(client, headers):
    fake = {
        "results": {
            "companies": [
                {
                    "company": {
                        "name": "ACME CORP",
                        "company_number": "123",
                        "jurisdiction_code": "us_de",
                        "current_status": "Active",
                        "company_type": "C-Corp",
                        "incorporation_date": "1990-01-01",
                        "registered_address_in_full": "1 Main St, Wilmington, DE",
                        "opencorporates_url": "https://opencorporates.com/companies/us_de/123",
                    }
                }
            ]
        }
    }
    with respx.mock(assert_all_called=False) as router:
        router.get("https://api.opencorporates.com/v0.4/companies/search").mock(
            return_value=httpx.Response(200, json=fake)
        )
        r = client.get(
            "/tools/search_companies",
            params={"name": "Acme", "state": "DE"},
            headers=headers,
        )
    body = _ok(r)
    assert body["success"] is True
    assert body["count"] == 1
    assert body["results"][0]["name"] == "ACME CORP"
    assert body["results"][0]["jurisdiction_code"] == "us_de"


def test_search_companies_uses_cache(client, headers):
    fake = {"results": {"companies": []}}
    with respx.mock(assert_all_called=False) as router:
        route = router.get(
            "https://api.opencorporates.com/v0.4/companies/search"
        ).mock(return_value=httpx.Response(200, json=fake))
        r1 = client.get(
            "/tools/search_companies",
            params={"name": "ZZTopCorp"},
            headers=headers,
        )
        r2 = client.get(
            "/tools/search_companies",
            params={"name": "ZZTopCorp"},
            headers=headers,
        )
    assert r1.status_code == 200 and r2.status_code == 200
    assert route.call_count == 1, "second call should hit local cache"
    assert r2.json().get("cached") is True


def test_search_sec_filings_normalizes(client, headers):
    fake = {
        "hits": {
            "hits": [
                {
                    "_id": "0001193125-21-000001:doc.htm",
                    "_source": {
                        "ciks": ["0000320193"],
                        "display_names": ["APPLE INC"],
                        "form": "10-K",
                        "file_date": "2021-10-29",
                    },
                }
            ]
        }
    }
    with respx.mock(assert_all_called=False) as router:
        router.get("https://efts.sec.gov/LATEST/search-index").mock(
            return_value=httpx.Response(200, json=fake)
        )
        r = client.get(
            "/tools/search_sec_filings",
            params={"company_name": "Apple", "form_type": "10-K"},
            headers=headers,
        )
    body = _ok(r)
    assert body["success"] is True
    assert body["results"][0]["accession_number"] == "0001193125-21-000001"
    assert body["results"][0]["company"] == "APPLE INC"
    assert body["results"][0]["url"].startswith(
        "https://www.sec.gov/Archives/edgar/data/0000320193/"
    )


def test_search_court_cases(client, headers):
    fake = {
        "results": [
            {
                "caseName": "Doe v. Roe",
                "court": "nyed",
                "docketNumber": "1:21-cv-00001",
                "dateFiled": "2021-01-01",
                "absolute_url": "/docket/12345/doe-v-roe/",
            }
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.get("https://www.courtlistener.com/api/rest/v4/search/").mock(
            return_value=httpx.Response(200, json=fake)
        )
        r = client.get(
            "/tools/search_court_cases",
            params={"party_name": "Doe"},
            headers=headers,
        )
    body = _ok(r)
    assert body["count"] == 1
    assert body["results"][0]["case_name"] == "Doe v. Roe"
    assert body["results"][0]["absolute_url"].startswith("https://www.courtlistener.com")


def test_lookup_federal_spending(client, headers):
    fake = {
        "results": [
            {
                "Award ID": "ABC-123",
                "Recipient Name": "ACME LLC",
                "Award Amount": 1234567.89,
                "Awarding Agency": "Department of Defense",
                "Awarding Sub Agency": "Army",
                "Award Type": "Contract",
                "Start Date": "2024-01-01",
                "End Date": "2024-12-31",
                "Description": "widgets",
            }
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.post(
            "https://api.usaspending.gov/api/v2/search/spending_by_award/"
        ).mock(return_value=httpx.Response(200, json=fake))
        r = client.get(
            "/tools/lookup_federal_spending",
            params={"recipient_name": "Acme", "year": 2024},
            headers=headers,
        )
    body = _ok(r)
    assert body["count"] == 1
    assert body["total_amount"] == pytest.approx(1234567.89)
    assert body["results"][0]["awarding_agency"] == "Department of Defense"


def test_lookup_npi(client, headers):
    fake = {
        "results": [
            {
                "number": "1234567893",
                "enumeration_type": "NPI-1",
                "basic": {
                    "first_name": "JANE",
                    "last_name": "SMITH",
                    "credential": "MD",
                },
                "addresses": [
                    {
                        "address_purpose": "LOCATION",
                        "city": "AUSTIN",
                        "state": "TX",
                        "telephone_number": "5125551234",
                    }
                ],
                "taxonomies": [
                    {"primary": True, "desc": "Internal Medicine"}
                ],
            }
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.get("https://npiregistry.cms.hhs.gov/api/").mock(
            return_value=httpx.Response(200, json=fake)
        )
        r = client.get(
            "/tools/lookup_npi",
            params={"name": "Smith", "state": "TX"},
            headers=headers,
        )
    body = _ok(r)
    assert body["success"] is True
    assert body["count"] == 1
    assert body["results"][0]["specialty"] == "Internal Medicine"
    assert body["results"][0]["state"] == "TX"


def test_get_ucc_filings_returns_not_implemented(client, headers):
    r = client.get(
        "/tools/get_ucc_filings",
        params={"debtor_name": "Acme", "state": "CA"},
        headers=headers,
    )
    body = _ok(r)
    assert body["success"] is False
    assert body["error"] == "not_implemented"


def test_verify_entity_aggregates(client, headers):
    oc_payload = {
        "results": {
            "companies": [
                {"company": {"name": "ACME", "jurisdiction_code": "us_de"}}
            ]
        }
    }
    sec_payload = {
        "hits": {
            "hits": [
                {
                    "_id": "0000000000-00-000000:doc.htm",
                    "_source": {
                        "ciks": ["1"],
                        "display_names": ["ACME"],
                        "form": "10-K",
                        "file_date": "2024-01-01",
                    },
                }
            ]
        }
    }
    spend_payload = {
        "results": [
            {"Award ID": "X", "Recipient Name": "ACME", "Award Amount": 1}
        ]
    }
    with respx.mock(assert_all_called=False) as router:
        router.get("https://api.opencorporates.com/v0.4/companies/search").mock(
            return_value=httpx.Response(200, json=oc_payload)
        )
        router.get("https://efts.sec.gov/LATEST/search-index").mock(
            return_value=httpx.Response(200, json=sec_payload)
        )
        router.post(
            "https://api.usaspending.gov/api/v2/search/spending_by_award/"
        ).mock(return_value=httpx.Response(200, json=spend_payload))
        r = client.get(
            "/tools/verify_entity",
            params={"name": "ACME", "state": "DE"},
            headers=headers,
        )
    body = _ok(r)
    assert body["success"] is True
    assert body["confidence"] == 100  # 40 + 30 + 30 capped
    assert set(body["sources"]) == {"opencorporates", "sec_edgar", "usa_spending"}
    assert body["verdict"] == "high_confidence_match"


def test_search_licenses_aggregates(client, headers):
    npi_payload = {
        "results": [
            {
                "number": "1",
                "enumeration_type": "NPI-2",
                "basic": {"organization_name": "MEMORIAL HOSPITAL"},
                "addresses": [
                    {"address_purpose": "LOCATION", "city": "AUSTIN", "state": "TX"}
                ],
                "taxonomies": [{"primary": True, "desc": "General Acute Care Hospital"}],
            }
        ]
    }
    fcc_payload = {
        "Licenses": {
            "License": [
                {
                    "callsign": "WABC",
                    "licName": "MEMORIAL HOSPITAL",
                    "categoryDesc": "Land Mobile",
                    "serviceDesc": "Industrial/Business",
                    "statusDesc": "Active",
                    "licState": "TX",
                    "frn": "0000000000",
                    "expiredDate": "12/31/2030",
                }
            ]
        }
    }
    with respx.mock(assert_all_called=False) as router:
        router.get("https://npiregistry.cms.hhs.gov/api/").mock(
            return_value=httpx.Response(200, json=npi_payload)
        )
        router.get(
            "https://data.fcc.gov/api/license-view/licenses/getLicenses"
        ).mock(return_value=httpx.Response(200, json=fcc_payload))
        r = client.get(
            "/tools/search_licenses",
            params={"entity_name": "Memorial Hospital", "state": "TX"},
            headers=headers,
        )
    body = _ok(r)
    assert body["success"] is True
    assert body["count"] >= 2
    assert "nppes_npi" in body["sources_hit"]
    assert "fcc" in body["sources_hit"]


def test_upstream_error_returns_envelope(client, headers):
    with respx.mock(assert_all_called=False) as router:
        router.get("https://api.opencorporates.com/v0.4/companies/search").mock(
            return_value=httpx.Response(503, text="upstream down")
        )
        r = client.get(
            "/tools/search_companies",
            params={"name": "FlakyCorp"},
            headers=headers,
        )
    body = _ok(r)  # tool layer never crashes; HTTP 200 with success=False
    assert body["success"] is False
    assert body["error"] in {"upstream_error", "source_unavailable"}


def test_usage_endpoint_reflects_calls(client, headers):
    # Burn one call
    with respx.mock(assert_all_called=False) as router:
        router.get("https://api.opencorporates.com/v0.4/companies/search").mock(
            return_value=httpx.Response(200, json={"results": {"companies": []}})
        )
        client.get(
            "/tools/search_companies",
            params={"name": "UsageProbe"},
            headers=headers,
        )
    r = client.get("/usage", headers=headers)
    body = _ok(r)
    assert body["tier"] == "free"
    assert body["calls_today"] >= 1
    assert body["remaining"] <= 29


def test_429_includes_upgrade_url(client, headers, monkeypatch):
    # Manually exhaust the dev key bucket
    from db.keys import FREE_DAILY_LIMIT, check_and_increment

    for _ in range(FREE_DAILY_LIMIT):
        check_and_increment("pubrecords-dev-key-001")

    r = client.get(
        "/tools/get_ucc_filings",
        params={"debtor_name": "X", "state": "CA"},
        headers=headers,
    )
    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["error"] == "rate_limit_exceeded"
    assert "mcpize.com/pubrecords-mcp" in detail["upgrade_url"]
