# PubRecords MCP — Launch Posts

> Brett owns posting + timing manually. Each draft below is ready to copy-paste.
> Production URL: <https://mcp-pubrecords-production.up.railway.app>
> Repo: <https://github.com/bch1212/mcp-pubrecords>
> Anthropic MCP Registry: `io.github.bch1212/pubrecords` (v0.1.0, listed)
> Free dev key: `pubrecords-dev-key-001` (30 calls/day)

---

## Show HN

**Title:** Show HN: PubRecords MCP – US public records intelligence for AI agents

**Body:**

I built a paid MCP server that aggregates US public-records APIs (OpenCorporates, SEC EDGAR, CourtListener, USASpending, NPPES, FCC) behind a uniform tool surface for AI agents doing due diligence, KYB, compliance, and sales research.

The thing that broke me was the inconsistency. Six APIs, six rate-limit headers, six response shapes, six failure modes. If you want an agent to verify a counterparty exists, surface their officers, find federal litigation history, and check contract awards, you used to need a babysitter. PubRecords MCP returns a normalized envelope from each source plus a cross-source `verify_entity` tool that hits OpenCorporates + EDGAR + USASpending in parallel and gives you a 0–100 confidence score.

Stack: FastAPI + the official `mcp` SDK (streamable-http transport) + httpx async + SQLite for a 24h response cache. Listed in the Anthropic MCP Registry as `io.github.bch1212/pubrecords`. 19 unit tests + 13 production smoke checks. Free dev key seeded — no signup to evaluate.

Live: https://mcp-pubrecords-production.up.railway.app/health
Repo: https://github.com/bch1212/mcp-pubrecords

Honest caveats in the README — UCC liens don't have a uniform federal API, so that tool returns `not_implemented` rather than fabricating data. State professional licenses outside healthcare and FCC are fragmented; documented per source.

Curious whether this clears the bar for "production agent infra" or if anything would change your mind.

---

## Reddit r/mcp

**Title:** Released a paid MCP for US public-records (companies, SEC, courts, federal spending, licenses)

**Body:**

Just shipped **PubRecords MCP** — a paid MCP server that aggregates the messy patchwork of US public-records APIs into one uniform tool surface for AI agents. Targeting due diligence / KYB / compliance / sales-research workflows.

**10 tools:**
- `search_companies` + `get_company_details` (OpenCorporates)
- `search_sec_filings` + `get_sec_filing` (EDGAR)
- `search_court_cases` (CourtListener / RECAP)
- `lookup_federal_spending` (USASpending.gov)
- `lookup_npi` (NPPES healthcare provider registry)
- `search_licenses` (NPI + FCC union)
- `get_ucc_filings` (returns `not_implemented` — state SOS APIs aren't uniform; honest)
- `verify_entity` — cross-source 0-100 confidence score (this is the headline)

Listed in the Anthropic MCP Registry as `io.github.bch1212/pubrecords` (v0.1.0). Free dev key seeded so you can try it without signup. $29/mo Pro or $0.03/call.

```
claude mcp add --transport http pubrecords-mcp https://mcp-pubrecords-production.up.railway.app/mcp/
```
Then set `X-API-Key: pubrecords-dev-key-001` in your client.

Code: https://github.com/bch1212/mcp-pubrecords

Open to feedback on the verify_entity heuristic and on which state-SOS UCC adapters to build first.

---

## Reddit r/ClaudeAI

**Title:** PubRecords MCP — give Claude SEC filings, federal court cases, and business records in one server

**Body:**

If you've been wiring up Claude for due diligence or compliance research, you know the pain of duct-taping six APIs together. I built **PubRecords MCP** to wrap them behind a single MCP server.

What you get when you add it to Claude:
- Search OpenCorporates business filings + officers
- Search SEC EDGAR (10-K/10-Q/8-K/S-1)
- Search federal court cases via CourtListener (RECAP)
- Search USASpending awards (federal contracts + grants)
- Look up healthcare providers (NPI registry)
- Look up FCC licenses
- Cross-reference an entity across all of these and get a confidence score

Install:
```
claude mcp add --transport http pubrecords-mcp https://mcp-pubrecords-production.up.railway.app/mcp/
```
Set X-API-Key in your client. Free dev key: `pubrecords-dev-key-001` (30 calls/day).

Code: https://github.com/bch1212/mcp-pubrecords

This is part of a broader push I'm making to ship MCP servers that real agentic workflows depend on. Roast it.

---

## Twitter / X

**Tweet 1 (announcement):**

new: PubRecords MCP

a paid MCP server that gives AI agents one tool surface for US public records:
- OpenCorporates business filings
- SEC EDGAR
- federal court cases (RECAP)
- USASpending awards
- NPI + FCC licenses
- cross-source verify_entity confidence score

free dev key seeded
🔗 https://github.com/bch1212/mcp-pubrecords

**Tweet 2 (how-to):**

claude mcp add --transport http pubrecords-mcp https://mcp-pubrecords-production.up.railway.app/mcp/

X-API-Key: pubrecords-dev-key-001

agents can now do KYB, due diligence, and compliance research without you babysitting six APIs

**Tweet 3 (the hot take):**

shipping MCPs that actually solve a workflow > shipping MCPs that wrap a single API

every agent doing due diligence needs:
✓ business filings
✓ SEC
✓ courts
✓ federal spending
✓ licenses

PubRecords MCP unifies all five behind one auth + cache + retry layer

---

## LinkedIn

I just shipped **PubRecords MCP** — a paid MCP server that aggregates US public-records APIs into a single, uniform tool surface for AI agents doing due diligence, KYB, compliance, and sales research.

**Why this matters for anyone building agentic workflows:** the data you need for entity verification lives across six federal sources (OpenCorporates, SEC EDGAR, CourtListener, USASpending, NPPES, FCC) — each with its own auth, rate limits, error semantics, and response shape. Your agent shouldn't have to babysit that.

**What's in the box:**
• 10 MCP tools spanning business filings, SEC reports, federal court cases, federal contracts/grants, healthcare provider registry, and FCC licenses
• A cross-source `verify_entity` tool that returns a 0–100 confidence score
• 24-hour response cache, async throughout, retry-on-429 with exponential backoff
• Listed in the Anthropic MCP Registry as `io.github.bch1212/pubrecords`
• Free dev tier so you can evaluate without signup

Production: https://mcp-pubrecords-production.up.railway.app/health
Code: https://github.com/bch1212/mcp-pubrecords

Pricing: free 30/day, Pro $29/mo, or $0.03/call metered.

Compliance note: only proxies public data; honest "not_implemented" envelopes where federal APIs don't exist (e.g. UCC liens) rather than fabricating coverage.

#MCP #ModelContextProtocol #AIAgents #DueDiligence #KYB #Anthropic

---

## Discord (#mcp / Anthropic Discord etc.)

🚀 just shipped PubRecords MCP — paid MCP server unifying US public records (OpenCorporates / SEC EDGAR / CourtListener / USASpending / NPI / FCC) for due-diligence/KYB agents.

10 tools + cross-source `verify_entity` confidence score. Listed in the Anthropic MCP Registry as `io.github.bch1212/pubrecords`. Free dev key seeded.

```
claude mcp add --transport http pubrecords-mcp https://mcp-pubrecords-production.up.railway.app/mcp/
```
X-API-Key: `pubrecords-dev-key-001`

Repo: https://github.com/bch1212/mcp-pubrecords

Feedback welcome — especially on the verify_entity scoring heuristic.

---

## Product Hunt

**Tagline:** US public records, ready for AI agents.

**Description:**

PubRecords MCP is a paid MCP server that turns the messy patchwork of US public-records APIs into a single, uniform tool surface for AI agents. One install, ten tools — search business entities, SEC filings, federal court cases, federal spending awards, healthcare providers, and FCC licenses. The headline tool is `verify_entity`, which cross-references a name across multiple sources and returns a 0–100 confidence score so agents doing due diligence, KYB, compliance, and sales research don't have to babysit six APIs.

**First comment (founder note):**

Hey PH — I'm Brett. Built this because every agent I wired up for due-diligence research kept fragmenting across six free APIs, each with its own auth, rate limits, and quirks. PubRecords MCP wraps them with a 24-hour cache, async retries, and one X-API-Key. Free dev key seeded — no signup required to evaluate. Listed in the Anthropic MCP Registry. Genuinely curious which state-SOS UCC API I should adapt first; vote in the comments.

**Topics:** Developer Tools, Artificial Intelligence, API, SaaS

---

## Hacker News (Ask HN follow-up if Show HN doesn't land)

**Title:** Ask HN: What's the right pricing model for a public-records MCP?

**Body:**

I just shipped PubRecords MCP — a paid MCP server that unifies six US public-records APIs (OpenCorporates / SEC EDGAR / CourtListener / USASpending / NPI / FCC) for AI agents doing KYB, due diligence, and compliance research.

Pricing today: free 30/day, $29/mo Pro, $0.03/call metered.

I'm torn on whether to (a) split into per-source bundles ($9 just-SEC, $9 just-courts, etc.) or (b) keep the unified product but raise the metered price. The reason agents pay for this isn't any one source — it's the cross-source `verify_entity` confidence score. But that's also the most expensive call.

What would you do?

Repo: https://github.com/bch1212/mcp-pubrecords

---

## Posting checklist (do these in order, manual)

1. ☐ Show HN — best Tuesday 8-10am ET
2. ☐ r/mcp post — same day, ~30min after Show HN
3. ☐ r/ClaudeAI post — within 24h
4. ☐ X thread — same day as Show HN
5. ☐ LinkedIn — next-day morning
6. ☐ Anthropic Discord #mcp-server-discussion — same day
7. ☐ Product Hunt — schedule for next Tuesday/Wednesday
8. ☐ Comment on relevant HN/Reddit threads about KYB/compliance tooling, mention if natural

**Do not:** mass-DM, cold-email developers about it (per agentfetch_no_cold_email memory — applies to all dev infra).
