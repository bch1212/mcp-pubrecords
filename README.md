# PubRecords MCP

[![status](https://img.shields.io/badge/status-live-brightgreen)](https://mcp-pubrecords-production.up.railway.app/health) [![mcp](https://img.shields.io/badge/MCP-streamable--http-blue)](https://mcp-pubrecords-production.up.railway.app/mcp/) [![price](https://img.shields.io/badge/price-%2429%2Fmo%20or%20%240.03%2Fcall-orange)](https://mcpize.com/pubrecords-mcp)

**Public-records intelligence for AI agents.** Aggregate US business filings, SEC reports, federal court cases, federal spending awards, and professional licenses through a single MCP server. Built for due diligence, compliance, sales research, and background checks.

---

## MCPize Listing Copy

> **PubRecords MCP** turns the patchwork of US public-records APIs into a single, predictable tool surface for AI agents. One call cross-references a company across OpenCorporates, SEC EDGAR, USASpending.gov, CourtListener (RECAP), the NPI registry, and FCC license-view — and returns a normalized confidence score so your agent doesn't need to babysit the messy bits. Every endpoint is async, retries upstream 429s with exponential backoff, and never crashes — failures come back as structured `{success: false, error: ...}` envelopes that downstream tools can branch on cleanly.
>
> Designed for **due diligence and KYB workflows, compliance and adverse-media checks, sales prospecting, and background research**. AI agents using PubRecords MCP can verify whether a counterparty actually exists, find their officers and registered agent, surface federal litigation history, see contract awards from Uncle Sam, and confirm professional licenses — all without juggling six different API keys, rate-limit headers, or response schemas. Cached 24 hours by default; most underlying records refresh daily at the source. Free tier (30 calls/day) for evaluation; Pro at $29/mo or $0.03/call for production traffic.

---

## Pricing

| Tier | Price | Limit |
|------|-------|-------|
| Free | $0 | 30 calls/day |
| Pro | **$29/mo** | Unlimited |
| Metered | **$0.03/call** | Pay-as-you-go |

Default dev key (free tier): `pubrecords-dev-key-001`

Upgrade: <https://mcpize.com/pubrecords-mcp>

---

## Tool Reference

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

---

## Install in Claude

```bash
claude mcp add --transport http pubrecords-mcp https://mcp-pubrecords-production.up.railway.app/mcp/
```

> **Note the trailing slash on `/mcp/`.** Without it the gateway issues a 307 that drops the POST body, breaking the JSON-RPC handshake.

Then set the API key in your client:

```
X-API-Key: pubrecords-dev-key-001
```

---

## Python SDK

A thin Python wrapper for non-MCP integrations is published on PyPI:

```bash
pip install pubrecords
```

```python
from pubrecords import PubRecords

client = PubRecords(api_key="pubrecords-dev-key-001")
print(client.health())
print(client.search_companies(name="Apple", state="CA"))
```

Source: [`pubrecords-sdk/`](./pubrecords-sdk). PyPI: <https://pypi.org/project/pubrecords/>.

---

## REST surface (mirrors the MCP tools)

All MCP tools are also available over plain HTTP for non-MCP clients:

```bash
curl -H "X-API-Key: pubrecords-dev-key-001" \
  "https://mcp-pubrecords-production.up.railway.app/tools/search_companies?name=Apple&state=CA"
```

Production URL: <https://mcp-pubrecords-production.up.railway.app>

```text
GET  /health                          (no auth)
GET  /usage                           (X-API-Key)
GET  /tools/<tool_name>?...           (X-API-Key)
POST /mcp/                            (MCP streamable-http transport)
```

`GET /usage` returns your remaining daily quota. `GET /health` is unauthenticated.

---

## Local development

```bash
git clone https://github.com/bch1212/mcp-pubrecords.git
cd mcp-pubrecords
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Run tests:

```bash
pytest -v
```

Optional environment variables (see `.env.example`):

- `PUBRECORDS_SEC_USER_AGENT` — SEC EDGAR requires an identifying UA. Set it in production.
- `OPENCORPORATES_TOKEN` — raises the OpenCorporates anonymous cap of ~50/month.
- `COURTLISTENER_TOKEN` — raises CourtListener's anonymous rate limit.
- `PUBRECORDS_CACHE_TTL` — cache TTL in seconds (default 86400 = 24h).
- `PUBRECORDS_ADMIN_TOKEN` — required to issue new keys at `/admin/keys`.

---

## Data freshness

Responses are cached for **24 hours** by default. Underlying source agencies update on different cadences:

| Source | Refresh cadence |
|--------|-----------------|
| OpenCorporates | Daily / weekly (varies by jurisdiction) |
| SEC EDGAR | Real-time (filings appear ~minutes after submission) |
| USASpending.gov | Monthly (FY-end backfills) |
| CourtListener (RECAP) | Daily (depends on volunteer uploads) |
| NPPES NPI | Weekly |
| FCC License-View | Daily |

For ultra-fresh queries, set `PUBRECORDS_CACHE_TTL=300` (5 minutes) — note that this will multiply your upstream API costs.

---

## Data Gaps & Source Limitations

These are honest caveats — the MCP returns structured `not_implemented` envelopes rather than fabricated data when a query falls outside coverage:

1. **UCC filings** — there is no uniform federal UCC API. Most state Secretary-of-State systems are HTML-only or require per-state credentials. `get_ucc_filings` returns `{"error": "not_implemented"}` until per-state adapters land (CA, DE, NY, TX are the priority backlog).
2. **State professional licenses** — covered for healthcare (NPI) and FCC. Other categories (bar, real estate, contractor, CPA) are state-by-state with no central API. `search_licenses` will say which sources matched.
3. **OpenCorporates rate limits** — anonymous traffic is capped at ~50 requests/month per IP. Set `OPENCORPORATES_TOKEN` for production. The 24h cache absorbs most of the burn.
4. **SEC EDGAR full-text** — `search_sec_filings` searches the body of filings, not just metadata, so query terms common across many filings can return wide result sets. Combine with `form_type` to narrow.
5. **CourtListener coverage** — federal only (PACER/RECAP). State court coverage is uneven and not guaranteed.
6. **No PII / consumer-record sources** — by design. PubRecords is for entity-level due diligence; consumer credit and identity data are deliberately out of scope.

---

## License & Compliance

This MCP only proxies and caches public records that are already free to access from federal sources. Cached payloads are kept for 24 hours and can be flushed by deleting the SQLite DB. No PII is stored beyond what the underlying public-record agencies already publish.
