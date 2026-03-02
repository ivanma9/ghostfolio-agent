# Benchmark Comparison Tool — Design

## Status: Approved
## Date: 2026-03-01

## Summary

Single tool `benchmark_comparison` that provides market context and portfolio-vs-benchmark performance comparison using two Ghostfolio endpoints:
- `GET /api/v1/benchmarks` — benchmark list with trends, market condition, ATH distance
- `GET /api/v1/benchmarks/{dataSource}/{symbol}/{startDate}` — benchmark performance time series (% change)

Originally scoped as two tools (benchmark_comparison + market_context), consolidated into one after discovering that `/api/v1/market-data/markets` only returns Fear & Greed index data, not broad market indices. The benchmarks endpoint provides the market context we need (S&P 500 trends, market conditions).

## API Contracts

### GET /api/v1/benchmarks (no auth required)

Response:
```json
{
  "benchmarks": [
    {
      "dataSource": "YAHOO",
      "marketCondition": "NEUTRAL_MARKET",  // ALL_TIME_HIGH | BEAR_MARKET | NEUTRAL_MARKET
      "name": "S&P 500",
      "performances": {
        "allTimeHigh": {
          "date": "2025-02-19T00:00:00.000Z",
          "performancePercent": -0.05  // decimal, -0.05 = -5%
        }
      },
      "symbol": "SPY",
      "trend50d": "UP",    // DOWN | NEUTRAL | UNKNOWN | UP
      "trend200d": "UP"
    }
  ]
}
```

### GET /api/v1/benchmarks/{dataSource}/{symbol}/{startDate} (auth required)

Path params: dataSource (e.g. "YAHOO"), symbol (e.g. "SPY"), startDate (yyyy-MM-dd)
Query params: range (1d, 1y, 5y, max, mtd, wtd, ytd)

Response:
```json
{
  "marketData": [
    { "date": "2025-01-02", "value": 0 },
    { "date": "2025-01-03", "value": 1.25 }
  ]
}
```

`value` = percentage change from start date (multiplied by 100, so 5.23 = +5.23%).

## Tool Design

### Parameters
- `benchmark` (str, default "SPY") — benchmark symbol to compare against
- `period` (str, default "ytd") — time range: 1d, 1y, 5y, ytd, max

### Period → Start Date Mapping
- `1d` → yesterday
- `ytd` → Jan 1 of current year
- `1y` → 365 days ago
- `5y` → 5 * 365 days ago
- `max` → 2000-01-01 (arbitrary far past)
- `mtd` → 1st of current month
- `wtd` → Monday of current week

### Flow
1. Parallel `asyncio.gather` of 3 calls:
   - `client.get_benchmarks()` — market context
   - `client.get_benchmark_detail(dataSource, symbol, startDate, range)` — benchmark time series
   - `client.get_portfolio_performance(range)` — portfolio performance
2. Extract benchmark from list (match by symbol), get trends/condition
3. Compute benchmark total return from last value in time series
4. Extract portfolio return % from performance response
5. Calculate alpha = portfolio return - benchmark return
6. Format output with market context + comparison + sampled timeline

### Output Format
```
Market & Benchmark Comparison (YTD)

Market Context:
  S&P 500 (SPY): Neutral Market, 5.2% from ATH
  50-Day Trend: UP | 200-Day Trend: UP

Performance Comparison (YTD):
  Your Portfolio:  +12.3% ($8,450.00)
  S&P 500 (SPY):  +9.8%
  Alpha:           +2.5% (outperforming)

Benchmark Timeline (sampled, 10 points):
  2025-01-02:  SPY +0.2%
  2025-02-01:  SPY +3.1%
  ...

[DATA_SOURCES: Ghostfolio]
```

### Error Handling
- Benchmark not found in list → "Benchmark '{symbol}' not available. Available: ..."
- Benchmark detail fails → still show market context from list
- Portfolio performance fails → still show benchmark data
- All fail → user-friendly error message

### Wiring
- New file: `src/ghostfolio_agent/tools/benchmark_comparison.py`
- New client methods in `src/ghostfolio_agent/clients/ghostfolio.py`:
  - `get_benchmarks() -> dict`
  - `get_benchmark_detail(data_source, symbol, start_date, range) -> dict`
- Register in `src/ghostfolio_agent/tools/__init__.py`
- Add to system prompt in `src/ghostfolio_agent/agent/graph.py`
- Cache: `@ttl_cache(ttl=300)` (5 minutes)
- Data source: `[DATA_SOURCES: Ghostfolio]`

## Test Plan

### Client Tests (~6 tests)
- get_benchmarks returns benchmark list
- get_benchmarks handles empty response
- get_benchmark_detail returns market data array
- get_benchmark_detail with range parameter
- API error handling (500, 403, timeout)

### Tool Tests (~15 tests)
- Basic comparison output with all data present
- Period mapping correctness (ytd → Jan 1, 1y → 365d ago, etc.)
- Benchmark symbol matching (case-insensitive)
- Benchmark not found → lists available benchmarks
- Portfolio fetch failure → still shows benchmark data
- Benchmark detail failure → still shows market context
- Both benchmark calls fail → graceful error
- Alpha calculation: positive (outperforming)
- Alpha calculation: negative (underperforming)
- Alpha calculation: equal (matching)
- Data source metadata line present
- Cache decorator applied
- Default parameters (SPY, ytd)
- Custom benchmark symbol
- Sampled timeline formatting (>20 points downsampled)

## Decisions
- **Merged market_context into this tool**: /market-data/markets only has Fear & Greed, not index data
- **Period computed, not user-supplied date**: Simpler UX, matches portfolio_performance tool pattern
- **SPY as default benchmark**: Most common portfolio benchmark for US equities
- **Ghostfolio-only data source**: No 3rd party API calls needed
