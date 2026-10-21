# pubrecords

Python client for **Halverson IQ Data** — one API key for US public records, Grants.gov opportunities, and SAM.gov contract notices.

For agentic use, install the MCP directly into Claude:

```bash
claude mcp add --transport http halverson-iq-data https://mcp-pubrecords-production.up.railway.app/mcp/
```

(Note the trailing slash on `/mcp/`.)

This Python SDK is for **non-MCP code** that wants the same data shape over plain HTTP.

## Install

```bash
pip install pubrecords
```

## Quickstart

Pass the per-user key you were issued. Do not embed a shared dev key.

```python
from pubrecords import PubRecords

with PubRecords(api_key="YOUR_API_KEY") as client:
    print(client.health())
    print(client.search_companies(name="Apple", state="CA"))
    print(client.search_grants(keyword="broadband"))
    print(client.verify_entity(name="Boeing"))
```

Async variant:

```python
import asyncio
from pubrecords import PubRecordsAsync

async def main():
    async with PubRecordsAsync(api_key="YOUR_API_KEY") as client:
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
| `search_grants(keyword, agency, amount_min, amount_max, status, limit)` | Grants.gov search |
| `get_grant_details(opportunity_id)` | One Grants.gov record |
| `search_contracts(keyword, naics_code, agency, set_aside, limit)` | SAM.gov solicitations |
| `get_contract_details(notice_id)` | One SAM.gov notice |
| `search_awards(recipient_name, agency, year)` | SAM.gov award notices |
| `get_agencies(type)` | Agencies with open grants and/or contracts |
| `get_deadlines(days_ahead)` | Grants closing soon |
| `match_opportunities(org_description, org_type, focus_areas, limit)` | Ranked grants + contracts |

## Pricing

One bill for every method on this client:

- Free: 30 calls/day on a per-user key.
- Pro: $29/mo unlimited at <https://mcpize.com/pubrecords-mcp>.
- Metered: $0.03/call.

## Repo

<https://github.com/bch1212/mcp-pubrecords>

## License

MIT
