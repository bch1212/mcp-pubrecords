# Halverson IQ Data

[![status](https://img.shields.io/badge/status-live-brightgreen)](https://mcp-pubrecords-production.up.railway.app/health) [![mcp](https://img.shields.io/badge/MCP-streamable--http-blue)](https://mcp-pubrecords-production.up.railway.app/mcp/) [![price](https://img.shields.io/badge/price-%2429%2Fmo%20or%20%240.03%2Fcall-orange)](https://mcpize.com/pubrecords-mcp)

**One paid MCP server for US public records, federal grants, and federal contracts.** Companies, SEC filings, court dockets, spending awards, licenses, Grants.gov opportunities, and SAM.gov contract notices share a single API key and a single bill.

---

## What this server includes

This repository is the combined Halverson IQ Data server.

| Source | Tools |
|--------|--------|
| OpenCorporates, SEC EDGAR, CourtListener, USASpending, NPPES, FCC | Public-records tools (companies, filings, courts, spending, licenses, entity verification) |
| Grants.gov | Grant search, details, agency rollup, deadline radar |
| SAM.gov | Contract search, notice details, award notices |

Not part of this server: business-intel and outdoor datasets (separate or retired), and web-page fetching (a different pipeline with its own fetchers and cache).

One customer key is checked on every tool. Free tier is 30 calls/day across the whole server. Pro is unlimited on the same key. Upgrade: <https://mcpize.com/pubrecords-mcp>

---

## Pricing

| Tier | Price | Limit |
|------|-------|-------|
| Free | $0 | 30 calls/day |
| Pro | **$29/mo** | Unlimited |
| Metered | **$0.03/call** | Pay-as-you-go |

Keys are issued per user. Ask the operator for a key, or have them mint one with `POST /admin/keys`. Examples below use the placeholder `YOUR_API_KEY`.

---

## Tool reference

### Public records

| Tool | Args | Returns |
|------|------|---------|
| `search_companies` | `name`, `state?`, `status?`, `limit?` | OpenCorporates entities |
| `get_company_details` | `company_id`, `jurisdiction` | Officers, registered agent, filings |
| `search_sec_filings` | `company_name`, `form_type?`, `date_from?`, `limit?` | EDGAR filing list |
| `get_sec_filing` | `accession_number` | Filing metadata + index URL |
| `search_court_cases` | `party_name`, `court?`, `date_from?`, `limit?` | RECAP federal dockets |
| `lookup_federal_spending` | `recipient_name`, `agency?`, `year?`, `limit?` | USASpending awards |
| `lookup_npi` | `name?`, `specialty?`, `state?`, `limit?` | NPPES providers |
| `get_ucc_filings` | `debtor_name`, `state` | UCC liens (roadmap — see Data Gaps) |
| `verify_entity` | `name`, `state?` | Cross-source 0–100 confidence score |
| `search_licenses` | `entity_name`, `license_type?`, `state?` | NPI + FCC license union |

### Grants and federal contracts

| Tool | Args | Returns |
|------|------|---------|
| `search_grants` | `keyword?`, `agency?`, `amount_min?`, `amount_max?`, `status?`, `limit?` | Grants.gov opportunities |
| `get_grant_details` | `opportunity_id` | Full Grants.gov record |
| `search_contracts` | `keyword?`, `naics_code?`, `agency?`, `set_aside?`, `limit?` | SAM.gov solicitations |
| `get_contract_details` | `notice_id` | One SAM.gov notice |
| `search_awards` | `recipient_name?`, `agency?`, `year?` | SAM.gov award notices |
| `get_agencies` | `type?` (`grants`, `contracts`, or `both`) | Agencies with open opportunities |
| `get_deadlines` | `days_ahead?` | Grants closing inside the window |
| `match_opportunities` | `org_description`, `org_type?`, `focus_areas?`, `limit?` | Top grants + contracts for an org profile |

`focus_areas` on the REST route is a comma-separated string. The MCP tool accepts a list.

Contract tools call SAM.gov only when `SAM_API_KEY` is set. If it is missing they return `{"success": false, "error": "SAM_API_KEY is not configured"}` and do not send a request.

---

## Install in Claude

```bash
claude mcp add --transport http halverson-iq-data https://mcp-pubrecords-production.up.railway.app/mcp/
```

> **Note the trailing slash on `/mcp/`.** Without it the gateway issues a 307 that drops the POST body, breaking the JSON-RPC handshake.

Then set the API key in your client:

```text
X-API-Key: YOUR_API_KEY
```

---

## Python SDK

A thin Python wrapper for non-MCP integrations lives in [`pubrecords-sdk/`](./pubrecords-sdk):

```bash
pip install pubrecords
```

```python
from pubrecords import PubRecords

client = PubRecords(api_key="YOUR_API_KEY")
print(client.health())
print(client.search_companies(name="Apple", state="CA"))
print(client.search_grants(keyword="broadband"))
```

---

## REST surface

Every MCP tool is also available over plain HTTP. Send the same `X-API-Key` on each call.

```bash
curl -H "X-API-Key: YOUR_API_KEY" \
  "https://mcp-pubrecords-production.up.railway.app/tools/search_companies?name=Apple&state=CA"

curl -H "X-API-Key: YOUR_API_KEY" \
  "https://mcp-pubrecords-production.up.railway.app/tools/search_grants?keyword=broadband"
```

Production URL: <https://mcp-pubrecords-production.up.railway.app>

```text
GET  /health                          (no auth)
GET  /usage                           (X-API-Key)
GET  /tools/<tool_name>?...           (X-API-Key)
POST /admin/keys                      (X-Admin-Token; fails closed)
POST /billing/upgrade                 (X-Admin-Token; fails closed)
POST /mcp/                            (MCP streamable-http transport)
```

`GET /usage` returns the remaining daily quota for that key. `GET /health` is unauthenticated.

### Issuing a customer key

`POST /admin/keys` and `POST /billing/upgrade` return **403** unless `PUBRECORDS_ADMIN_TOKEN` is set and the `X-Admin-Token` header matches it. There is no default admin token.

```bash
curl -X POST https://mcp-pubrecords-production.up.railway.app/admin/keys \
  -H "X-Admin-Token: $PUBRECORDS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"YOUR_API_KEY","tier":"free"}'
```

Promote that same key to the paid tier (this is the single billing switch):

```bash
curl -X POST https://mcp-pubrecords-production.up.railway.app/billing/upgrade \
  -H "X-Admin-Token: $PUBRECORDS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"YOUR_API_KEY"}'
```

---

## Local development

```bash
git clone https://github.com/bch1212/mcp-pubrecords.git
cd mcp-pubrecords
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn server:app --reload --port 8000
```

Run tests:

```bash
pytest -v
```

Environment variables (see `.env.example`):

| Variable | Required | Purpose |
|----------|----------|---------|
| `PUBRECORDS_ADMIN_TOKEN` | Yes, to issue or upgrade keys | Admin secret. Missing or blank fails closed (403). |
| `SAM_API_KEY` | Yes, for contract tools | Your SAM.gov key. Never commit a real value. |
| `PUBRECORDS_SEC_USER_AGENT` | Production | Identifying User-Agent for SEC EDGAR. |
| `OPENCORPORATES_TOKEN` | No | Raises the OpenCorporates anonymous cap. |
| `COURTLISTENER_TOKEN` | No | Raises the CourtListener anonymous cap. |
| `PUBRECORDS_CACHE_TTL` | No | Cache TTL in seconds (default 86400). |
| `PUBRECORDS_DB_PATH` | No | SQLite file for cache and API keys. |
| `PORT` | No | Listen port. Railway sets this. |

---

## Data freshness

Responses are cached for **24 hours** by default.

| Source | Refresh cadence |
|--------|-----------------|
| OpenCorporates | Daily / weekly (varies by jurisdiction) |
| SEC EDGAR | Filings appear minutes after submission |
| USASpending.gov | Monthly, with fiscal-year backfills |
| CourtListener (RECAP) | Daily, depending on uploads |
| NPPES NPI | Weekly |
| FCC License-View | Daily |
| Grants.gov | Posted opportunities, as the agency updates them |
| SAM.gov | Contract notices, as contracting offices post them |

For fresher queries, set `PUBRECORDS_CACHE_TTL=300` (5 minutes). That multiplies upstream traffic.

---

## Data gaps and source limits

The server returns a structured error envelope instead of invented rows when a query is outside coverage.

1. **UCC filings** — there is no uniform federal UCC API. `get_ucc_filings` returns `{"error": "not_implemented"}` until per-state adapters land.
2. **State professional licenses** — healthcare (NPI) and FCC are covered. Bar, real estate, contractor, and CPA licenses are state-by-state.
3. **OpenCorporates rate limits** — anonymous traffic is capped. Set `OPENCORPORATES_TOKEN` for production.
4. **SEC EDGAR full-text** — broad terms return wide sets. Combine with `form_type`.
5. **CourtListener** — federal PACER/RECAP. State courts are not guaranteed.
6. **SAM.gov** — contract tools do nothing until `SAM_API_KEY` is set in the environment. Apply at <https://sam.gov>. The key is not embedded in this repo.
7. **SAM award history** — `search_awards` reads Award Notice rows from the opportunities API. Deeper recipient rollups stay on `lookup_federal_spending` (USASpending).
8. **Match scores** — `match_opportunities` is deterministic token overlap on title and agency. It does not call a model.
9. **No consumer PII** — entity-level public records only.

---

## License and compliance

This server proxies and caches public records that are already free to access from federal and public sources. Cached payloads are kept for 24 hours and can be flushed by deleting the SQLite file. Customer API keys and the admin token belong in the environment and the SQLite key store. Do not commit them.
