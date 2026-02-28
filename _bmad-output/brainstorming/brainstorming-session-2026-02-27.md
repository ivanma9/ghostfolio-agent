---
stepsCompleted: [1, 2, 3]
inputDocuments: ['docs/plans/2026-02-24-new-tools-design.md', 'src/ghostfolio_agent/clients/ghostfolio.py']
session_topic: '3rd Party API Clients: Enriching Holdings with External Market Intelligence'
session_goals: 'Identify the right external data providers for analyst data, news sentiment, earnings, insider trading, and congressional activity; map each signal to planned features; decide which free-tier endpoints to use vs. skip'
selected_approach: 'User-Selected Techniques'
techniques_used: ['Signal Mapping', 'Free Tier Feasibility Filter']
ideas_generated: ['FMP /stable endpoints replace legacy v3/v4 and are more stable', 'Finnhub free tier covers analyst recs and earnings calendar', 'Alpha Vantage covers news sentiment and macro indicators on free tier', 'Congressional trading data deserves its own dedicated service due to scraping complexity', 'Insider trading from FMP is premium-only — replace with price target consensus/summary', 'Parallel asyncio.gather for enrichment fetches prevents latency stacking in holding_detail']
context_file: 'docs/plans/2026-02-24-new-tools-design.md'
---

# Brainstorming Session Results

**Facilitator:** Ivanma
**Date:** 2026-02-27

## Session Overview

**Topic:** 3rd Party API Clients — Enriching Holdings with External Market Intelligence

**Goals:** Identify external data providers to enrich the `holding_detail` tool and support future features (#2 Smart Holding Deep Dive, #3 Morning Briefing, #4 Conviction Score, #6 Alert Engine). Evaluate free-tier feasibility for each data signal. Map signals to providers and decide what ships now vs. later.

### Context Guidance

_The agent currently answers portfolio questions using only Ghostfolio data. The next evolution is to layer in external market intelligence — analyst ratings, earnings dates, news sentiment, price targets, and potentially alternative data like congressional trades and insider transactions. The challenge is doing this within free-tier API limits while keeping the architecture simple._

_Three providers are under consideration: Financial Modeling Prep (FMP), Finnhub, and Alpha Vantage. A fourth signal — congressional trading data — is attractive but has no clean free API and would require scraping or a dedicated service._

### Session Setup

_Session focused on mapping data signals to providers, filtering by free-tier availability, and deciding integration approach. The holding_detail tool is the immediate integration target. Future features (Morning Briefing, Conviction Score, Alert Engine) will consume the same clients._

## Technique Selection

**Approach:** User-Selected Techniques
**Selected Techniques:**

- **Signal Mapping**: Map each desired data signal to available providers, noting free vs. premium tier status
- **Free Tier Feasibility Filter**: For each provider+signal pair, confirm free tier access before committing

---

## Signal Mapping Results

### Desired Signals

| Signal | Why It Matters | Provider Candidates |
|--------|---------------|---------------------|
| Analyst recommendations | Buy/hold/sell consensus from Wall Street | Finnhub, FMP |
| Earnings calendar | Upcoming EPS dates and estimates | Finnhub, Alpha Vantage |
| News sentiment | Market narrative for a holding | Alpha Vantage |
| Price targets | Street's implied upside/downside | FMP |
| Insider trading | Management conviction signals | FMP, SEC EDGAR |
| Congressional trading | Alternative data: political alpha | Quiver Quant, Capitol Trades, custom scraper |
| Macro indicators | Fed rate, CPI, treasury yields | Alpha Vantage |
| Analyst EPS/revenue estimates | Forward-looking fundamentals | FMP |

### Provider Decisions

#### Financial Modeling Prep (FMP)

- **Base URL:** `https://financialmodelingprep.com/stable` (new stable endpoint prefix — replaces legacy `/api/v3` and `/api/v4`)
- **Free tier includes:** analyst estimates (annual), price target consensus, price target summary
- **Premium only:** insider trading transactions, institutional ownership, Senate/House trading (these require paid subscription)
- **Decision:** Use `/stable` endpoints. Include analyst estimates + price target consensus + price target summary. Drop insider trading — premium gate confirmed.

#### Finnhub

- **Base URL:** `https://finnhub.io/api/v1`
- **Free tier includes:** analyst recommendations (trend by period), earnings calendar
- **Premium only:** congressional trading (`/stock/congressional-trading`), Senate/House trading endpoints
- **Decision:** Use analyst recommendations and earnings calendar. Drop congressional trading — premium gate confirmed.

#### Alpha Vantage

- **Base URL:** `https://www.alphavantage.co/query`
- **Free tier includes:** news sentiment (NEWS_SENTIMENT), Fed Funds Rate, CPI, Treasury Yield
- **Rate limit:** 25 requests/day on free tier — acceptable for on-demand enrichment, not suitable for bulk polling
- **Decision:** Use news sentiment for holding enrichment. Include macro indicators (Fed rate, CPI, yield) for Morning Briefing macro context.

#### Congressional Trading Data

- **Free options:** None with a clean JSON API. Quiver Quant has a free tier but with tight limits and no guarantee of stability. House/Senate disclosure sites require scraping.
- **Complexity:** Scraping disclosure PDFs is a standalone engineering problem — parsers, deduplication, name matching to ticker symbols.
- **Decision:** Do NOT integrate into this agent codebase. Build as a **separate standalone service** that exposes a clean REST API. The agent will eventually call that service's API as a 4th enrichment source. This is tracked as its own task (#10).

---

## Integration Architecture

### holding_detail Tool Enrichment

The `holding_detail` tool runs 5 parallel async fetches when all 3 clients are configured:

```
asyncio.gather(
    finnhub.get_earnings_calendar(symbol),      # upcoming EPS dates
    finnhub.get_analyst_recommendations(symbol), # buy/hold/sell counts
    alpha_vantage.get_news_sentiment(symbol),    # news headlines + sentiment
    fmp.get_price_target_consensus(symbol),      # street consensus
    fmp.get_price_target_summary(symbol),        # 1mo / 1Q analyst counts
)
```

Clients are optional — if an API key is not configured, that enrichment is silently skipped. This allows graceful degradation.

### Client Factory Pattern

Each client is a simple async `httpx`-based class instantiated in `graph.py` when its API key is present. No dependency injection framework needed.

### Feature Readiness

| Feature | Required Signals | Status |
|---------|----------------|--------|
| #2 Smart Holding Deep Dive | earnings, analyst recs, news, price targets | Ready (no congressional needed for v1) |
| #3 Morning Briefing | news sentiment, earnings calendar, macro | Ready |
| #4 Conviction Score | analyst recs, price targets, news sentiment | Ready |
| #5 Why Did Portfolio Move | news sentiment, macro indicators | Ready |
| #6 Alert Engine | earnings calendar, analyst recs, price targets | Ready |
| #10 Congressional Trading Datastore | congressional trades | Separate service — future integration |

---

## Key Insights

1. **FMP /stable is the right base URL.** The legacy `/api/v3` and `/api/v4` paths work but are being superseded. `/stable` is the canonical modern endpoint prefix and should be used from the start.

2. **Premium gates are real.** Both FMP insider trading and Finnhub congressional trading require paid plans. Rather than designing around hoped-for access, those signals are simply dropped or deferred.

3. **Congressional data is a separate problem.** The scraping + parsing + symbol matching work is significant enough that it belongs in its own service. Embedding it in this agent would add complexity with no free API to rely on.

4. **Parallel fetches are essential.** Five API calls in serial would add ~5 seconds of latency. `asyncio.gather` with individual error handling keeps holding_detail responsive.

5. **Free tier rate limits favor on-demand, not polling.** Alpha Vantage's 25 req/day limit means Morning Briefing and Alert Engine must be intelligent about which symbols to enrich, not bulk-scan the portfolio on every tick.

---

## Session Completion

**Total Ideas Generated:** 6 key architectural insights
**Technique Effectiveness:** Signal mapping efficiently surfaced premium gates; free-tier filter eliminated candidates early
**Outcome:** Clear provider decisions made; congressional data correctly scoped out to a separate service; integration architecture defined for holding_detail

**Next Step:** Implement the three client classes and wire into holding_detail tool with parallel enrichment

---

## Architecture Decisions (added 2026-02-28)

The following decisions were made after this session and supersede or clarify the above:

- **Congressional trading → separate standalone repo/service.** The decision to exclude congressional data from this codebase is confirmed and formalized. It will be built as a completely separate repository/service, not just a separate module. The agent will integrate with it via API call when that service is ready. Task #10 is a placeholder for that integration point.
- **FMP migrated from legacy /api/v3 and /api/v4 to /stable endpoints.** The `FMPClient` base URL is `https://financialmodelingprep.com/stable`. All three FMP methods (`get_analyst_estimates`, `get_price_target_consensus`, `get_price_target_summary`) use `/stable` paths.
- **FMP insider trading removed — premium only.** Initially considered, now confirmed dropped. Replaced by price target consensus and price target summary, which are available on the free tier and provide overlapping signal (street conviction on a stock).
- **Finnhub congressional trading removed — premium only.** The `/stock/congressional-trading` endpoint requires a paid Finnhub plan. Dropped entirely from this codebase. Congressional data will come from the standalone service (Task #10) when ready.
- **Features #2, #3, #4, #6 ship without congressional data.** Smart Holding Deep Dive, Morning Briefing, Conviction Score, and Alert Engine will launch using earnings + analyst recs + news sentiment + price targets. Congressional data will be added as an incremental enrichment layer once the standalone service is available.
