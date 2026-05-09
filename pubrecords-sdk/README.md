# pubrecords

Python client for the **PubRecords MCP** — public-records intelligence for AI agents (US business filings, SEC EDGAR, federal courts, federal spending, healthcare/FCC licenses).

For agentic use, install the MCP directly into Claude:

```bash
claude mcp add --transport http pubrecords-mcp https://mcp-pubrecords-production.up.railway.app/mcp/
```

(Note the trailing slash on `/mcp/`.)

This Python SDK is for **non-MCP code** that wants the same data shape over plain HTTP.

## Install

```bash
pip install pubrecords
```

## Quickstart

```python
from pubrecords import PubRecords

with PubRecords(api_key="pubrecords-dev-key-001") as client:
    print(client.health())
    print(client.search_companies(name="Apple", state="CA"))
    print(client.verify_entity(name="Boeing"))
```

Async variant:

```python
import asyncio
from pubrecords import PubRecordsAsync

async def main():
    async with PubRecordsAsync() as client:
        print(await client.search_sec_filings("Apple", form_type="10-K"))

asyncio.run(main())
```

## Tools

| Method | Description |
|--------|-------------|
| `search_companies(name, state, status, limit)` | OpenCorporates entity search |
| `get_company_details(company_id, jurisdiction)` | Officers, agent, filings |
| `search_sec_filings(company_name, form_type, date_from, limit)` | SEC EDGAR full-text |
| `get_sec_filing(accession_number)` | Filing metadata + index URL |
| `search_court_cases(party_name, court, date_from, limit)` | RECAP federal dockets |
| `lookup_federal_spending(recipient_name, agency, year, limit)` | USASpending awards |
| `lookup_npi(name, specialty, state, limit)` | NPPES providers |
| `get_ucc_filings(debtor_name, state)` | UCC liens (roadmap) |
| `verify_entity(name, state)` | Cross-source confidence score |
| `search_licenses(entity_name, license_type, state)` | NPI + FCC license union |

## Pricing

- Free: 30 calls/day with the seeded dev key (`pubrecords-dev-key-001`).
- Pro: $29/mo unlimited at <https://mcpize.com/pubrecords-mcp>.
- Metered: $0.03/call.

## Repo

<https://github.com/bch1212/mcp-pubrecords>

## License

MIT
