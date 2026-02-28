# 3rd Party API Clients: Finnhub, Alpha Vantage, FMP

**Date:** 2026-02-27
**Status:** Implemented
**Type:** Infrastructure — 3 New Async HTTP Clients + holding_detail Enrichment

## Summary

Add three external market data clients to enrich the `holding_detail` tool with analyst intelligence, news sentiment, earnings dates, and price targets. Clients are optional — if an API key is absent, that enrichment is silently skipped. All fetches run in parallel via `asyncio.gather`.

**Providers:**
- **Finnhub** — analyst recommendation trends, earnings calendar
- **Alpha Vantage** — news sentiment, macro indicators (Fed rate, CPI, treasury yield)
- **Financial Modeling Prep (FMP)** — analyst estimates (annual), price target consensus, price target summary

---

## Client 1: FMP (`src/ghostfolio_agent/clients/fmp.py`)

**Base URL:** `https://financialmodelingprep.com/stable`

Note: FMP uses the `/stable` endpoint prefix (not the legacy `/api/v3` or `/api/v4` paths). All methods are available on the free tier.

### Methods

| Method | Endpoint | Returns |
|--------|----------|---------|
| `get_analyst_estimates(symbol)` | `/stable/analyst-estimates?period=annual` | List of annual EPS and revenue forecasts |
| `get_price_target_consensus(symbol)` | `/stable/price-target-consensus` | Consensus, median, high, low target prices |
| `get_price_target_summary(symbol)` | `/stable/price-target-summary` | Analyst counts and average targets by time period |

### Not included (premium only)
- Insider trading transactions — requires paid FMP plan

### Implementation
```python
class FMPClient:
    BASE_URL = "https://financialmodelingprep.com/stable"

    async def get_analyst_estimates(self, symbol: str) -> list[dict]: ...
    async def get_price_target_consensus(self, symbol: str) -> list[dict]: ...
    async def get_price_target_summary(self, symbol: str) -> list[dict]: ...
```

---

## Client 2: Finnhub (`src/ghostfolio_agent/clients/finnhub.py`)

**Base URL:** `https://finnhub.io/api/v1`

### Methods

| Method | Endpoint | Returns |
|--------|----------|---------|
| `get_analyst_recommendations(symbol)` | `/stock/recommendation` | List of recommendation periods with buy/hold/sell counts |
| `get_earnings_calendar(symbol)` | `/calendar/earnings` | List of upcoming earnings events with EPS estimates |

### Not included (premium only)
- Congressional trading (`/stock/congressional-trading`) — requires paid Finnhub plan

### Implementation
```python
class FinnhubClient:
    BASE_URL = "https://finnhub.io/api/v1"

    async def get_analyst_recommendations(self, symbol: str) -> list[dict]: ...
    async def get_earnings_calendar(self, symbol: str) -> list[dict]: ...
```

---

## Client 3: Alpha Vantage (`src/ghostfolio_agent/clients/alpha_vantage.py`)

**Base URL:** `https://www.alphavantage.co/query` (single query endpoint, function param selects data type)

**Rate limit:** 25 requests/day on free tier.

### Methods

| Method | AV Function | Returns |
|--------|-------------|---------|
| `get_news_sentiment(ticker)` | `NEWS_SENTIMENT` | News feed with sentiment labels per article |
| `get_fed_funds_rate()` | `FEDERAL_FUNDS_RATE` | Daily Fed Funds effective rate |
| `get_cpi()` | `CPI` | Monthly Consumer Price Index |
| `get_treasury_yield(maturity)` | `TREASURY_YIELD` | Daily treasury yield by maturity |

### Implementation
```python
class AlphaVantageClient:
    BASE_URL = "https://www.alphavantage.co/query"

    async def get_news_sentiment(self, ticker: str) -> list[dict]: ...
    async def get_fed_funds_rate(self) -> list[dict]: ...
    async def get_cpi(self) -> list[dict]: ...
    async def get_treasury_yield(self, maturity: str = "10year") -> list[dict]: ...
```

---

## holding_detail Tool Enrichment (`src/ghostfolio_agent/tools/holding_detail.py`)

The `holding_detail` tool accepts the three clients as optional constructor parameters and runs parallel enrichment fetches when clients are present.

### Parallel Fetch Pattern

```python
enrichment_tasks = []
task_labels = []

if finnhub:
    enrichment_tasks.append(_safe_fetch(finnhub.get_earnings_calendar(symbol), "finnhub_earnings"))
    task_labels.append("earnings")
    enrichment_tasks.append(_safe_fetch(finnhub.get_analyst_recommendations(symbol), "finnhub_analyst"))
    task_labels.append("analyst")

if alpha_vantage:
    enrichment_tasks.append(_safe_fetch(alpha_vantage.get_news_sentiment(symbol), "av_news"))
    task_labels.append("news")

if fmp:
    enrichment_tasks.append(_safe_fetch(fmp.get_price_target_consensus(symbol), "fmp_pt_consensus"))
    task_labels.append("pt_consensus")
    enrichment_tasks.append(_safe_fetch(fmp.get_price_target_summary(symbol), "fmp_pt_summary"))
    task_labels.append("pt_summary")

if enrichment_tasks:
    results = await asyncio.gather(*enrichment_tasks)
    enrichment = dict(zip(task_labels, results))
```

`_safe_fetch` catches all exceptions and returns `None`, so a single provider outage does not break the entire response.

### Output Sections (when data available)

1. **Upcoming Earnings** — date, EPS estimate, EPS actual (up to 3 entries)
2. **Analyst Consensus** — period, strong buy / buy / hold / sell / strong sell counts
3. **News Sentiment** — up to 5 headlines with sentiment label and source
4. **Price Targets** — consensus, median, high, low; plus last-month and last-quarter analyst counts and averages

---

## Config Changes (`src/ghostfolio_agent/config.py`)

Three new optional settings added:

```python
finnhub_api_key: str = ""
alpha_vantage_api_key: str = ""
fmp_api_key: str = ""
```

If a key is empty string, the corresponding client is not instantiated and enrichment is silently skipped.

---

## Agent Graph Changes (`src/ghostfolio_agent/agent/graph.py`)

Client instantiation and optional passing into `create_holding_detail_tool`:

```python
finnhub_client = FinnhubClient(settings.finnhub_api_key) if settings.finnhub_api_key else None
alpha_vantage_client = AlphaVantageClient(settings.alpha_vantage_api_key) if settings.alpha_vantage_api_key else None
fmp_client = FMPClient(settings.fmp_api_key) if settings.fmp_api_key else None

holding_detail = create_holding_detail_tool(ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client)
```

---

## Files Changed

### New files (3):
- `src/ghostfolio_agent/clients/finnhub.py`
- `src/ghostfolio_agent/clients/alpha_vantage.py`
- `src/ghostfolio_agent/clients/fmp.py`

### Modified files (4):
- `src/ghostfolio_agent/tools/holding_detail.py` — parallel enrichment integration
- `src/ghostfolio_agent/agent/graph.py` — client instantiation
- `src/ghostfolio_agent/config.py` — 3 new optional API key settings
- `.env.example` — document new keys

---

## Out of Scope: Congressional Trading Data

Congressional trading data was evaluated and explicitly excluded from this implementation:

- No clean free JSON API exists (Finnhub congressional endpoint is premium; Quiver Quant has tight limits)
- Reliable data requires scraping House/Senate disclosure sites — a standalone engineering problem
- This work is tracked as **Task #10: Build Congressional Trading Datastore** as a separate standalone service

When Task #10 is complete, the agent will integrate with that service's API as a 4th enrichment source in `holding_detail` and a data feed for the Alert Engine and Morning Briefing.

---

## Implementation Steps

1. Create `FinnhubClient` with analyst recs + earnings calendar methods
2. Create `AlphaVantageClient` with news sentiment + macro indicator methods
3. Create `FMPClient` with analyst estimates + price target consensus + summary (using `/stable` endpoints)
4. Add 3 optional API key settings to `config.py`
5. Update `holding_detail.py` with parallel enrichment fetch pattern
6. Wire optional clients through `graph.py`
7. Update `.env.example` with new key names

---

## Architecture Updates (added 2026-02-28)

The following decisions were finalized after initial implementation and supersede any earlier notes:

- **Congressional trading → separate standalone repo/service, not a module in this codebase.** The exclusion is architectural, not just a deferred TODO. Task #10 is a placeholder for the integration point once that service ships.
- **FMP base URL is `/stable` (not legacy `/api/v3` or `/api/v4`).** All three FMP methods target `https://financialmodelingprep.com/stable`. The legacy paths were considered and explicitly not used.
- **FMP insider trading removed — premium only.** Replaced by price target consensus + price target summary, which cover street conviction on the free tier.
- **Finnhub congressional trading removed — premium only.** The `/stock/congressional-trading` endpoint is behind a paid plan. Dropped entirely. Congressional data will come from the standalone service (Task #10).
- **Features #2 Smart Holding Deep Dive, #3 Morning Briefing, #4 Conviction Score, and #6 Alert Engine ship without congressional data.** The enrichment set of earnings + analyst recs + news sentiment + price targets is sufficient for v1 of each feature. Congressional data is an incremental addition once the standalone service is available.
