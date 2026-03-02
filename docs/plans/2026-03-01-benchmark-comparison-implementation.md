# Benchmark Comparison — Implementation Plan

## Execution Strategy

Two parallel agents, then a final wiring step:

- **Agent 1**: Client methods + client tests
- **Agent 2**: Tool implementation + tool tests
- **Sequential finish**: Wire into __init__.py and graph.py, run full test suite

Agent 2 can stub the client calls (AsyncMock) so it doesn't depend on Agent 1 being complete.

---

## Agent 1 Prompt: Client Methods + Tests

```
You are implementing two new methods on the GhostfolioClient class in an existing Python project.

## Context
- Project: /Users/ivanma/Desktop/gauntlet/AgentForge
- Client file: src/ghostfolio_agent/clients/ghostfolio.py
- Client inherits from BaseClient which provides _get() and _post() methods
- Existing methods follow the pattern: async def method() -> dict, calling self._get(path, params=...)
- Tests use respx for HTTP mocking and pytest

## Task: Add Two Client Methods

### 1. get_benchmarks()
- Endpoint: GET /api/v1/benchmarks
- No parameters
- Returns: dict with "benchmarks" key containing list of benchmark objects
- Each benchmark has: dataSource, symbol, name, marketCondition, performances, trend50d, trend200d

### 2. get_benchmark_detail(data_source: str, symbol: str, start_date: str, date_range: str = "max")
- Endpoint: GET /api/v1/benchmarks/{data_source}/{symbol}/{start_date}
- Query param: range={date_range}
- Returns: dict with "marketData" key containing list of {date, value} objects
- value = percentage change from start date (already * 100)

## Tests to Write

Create tests/unit/test_ghostfolio_benchmarks.py with:
1. test_get_benchmarks_returns_list — mock GET /api/v1/benchmarks, verify response parsed
2. test_get_benchmarks_empty — mock empty benchmarks array
3. test_get_benchmark_detail_returns_market_data — mock with date range
4. test_get_benchmark_detail_default_range — verify "max" is default
5. test_get_benchmark_detail_custom_range — verify range param passed
6. test_get_benchmarks_api_error — mock 500, verify raises TransientError
7. test_get_benchmark_detail_auth_error — mock 403, verify raises AuthenticationError

## Patterns to Follow
- Look at existing methods in ghostfolio.py for exact style
- Tests: look at tests/unit/test_fmp_client.py for respx mocking pattern
- Base URL is self.base_url (set in __init__), client uses _get() from BaseClient
- The GhostfolioClient base_url includes the Ghostfolio host (e.g. http://localhost:3333)
- Import exceptions from ghostfolio_agent.clients.exceptions

## Verification
Run: uv run pytest tests/unit/test_ghostfolio_benchmarks.py -v
All tests must pass.

DO NOT modify __init__.py or graph.py — that will be done separately.
```

---

## Agent 2 Prompt: Tool Implementation + Tests

```
You are implementing a new benchmark_comparison tool for a Ghostfolio AI agent.

## Context
- Project: /Users/ivanma/Desktop/gauntlet/AgentForge
- Tool pattern: see src/ghostfolio_agent/tools/stock_quote.py and portfolio_performance.py
- Tools are factory functions: create_X_tool(client, ...) that return a @tool decorated async function
- Use @ttl_cache(ttl=300) decorator (from ghostfolio_agent.tools.cache)
- Use structlog for logging
- Client methods will be: client.get_benchmarks() and client.get_benchmark_detail(ds, sym, start_date, range)

## Task: Create src/ghostfolio_agent/tools/benchmark_comparison.py

### Function Signature
```python
def create_benchmark_comparison_tool(client: GhostfolioClient):
    @tool
    @ttl_cache(ttl=300)
    async def benchmark_comparison(benchmark: str = "SPY", period: str = "ytd") -> str:
        """Compare your portfolio performance against a market benchmark..."""
```

### Period → Start Date Mapping
```python
from datetime import date, timedelta

PERIOD_TO_START = {
    "1d": lambda: (date.today() - timedelta(days=1)).isoformat(),
    "ytd": lambda: date(date.today().year, 1, 1).isoformat(),
    "mtd": lambda: date(date.today().year, date.today().month, 1).isoformat(),
    "1y": lambda: (date.today() - timedelta(days=365)).isoformat(),
    "5y": lambda: (date.today() - timedelta(days=5*365)).isoformat(),
    "max": lambda: "2000-01-01",
}
```

### Period → Ghostfolio Range Mapping (for portfolio_performance)
```python
PERIOD_TO_RANGE = {
    "1d": "1d",
    "ytd": "ytd",
    "mtd": "1m",  # closest available
    "1y": "1y",
    "5y": "max",  # closest available
    "max": "max",
}
```

### Flow
1. Compute start_date from period
2. Parallel asyncio.gather of 3 calls (use safe_fetch from ghostfolio_agent.utils for benchmark calls):
   a. client.get_benchmarks() — for market context
   b. client.get_benchmark_detail(data_source, benchmark, start_date, period) — benchmark time series
   c. client.get_portfolio_performance(range) — portfolio returns

   NOTE: For get_benchmark_detail, we need dataSource. First try to find it from benchmarks list.
   Since benchmarks list and detail are dependent, do it in 2 phases:
   - Phase 1: get_benchmarks() + get_portfolio_performance() in parallel
   - Phase 2: get_benchmark_detail() using dataSource from phase 1

3. Find matching benchmark in list (case-insensitive symbol match)
4. If benchmark not found, return available benchmarks list
5. Extract from benchmarks list: marketCondition, trend50d, trend200d, ATH distance
6. Extract benchmark total return = last value in marketData array
7. Extract portfolio return % from performance response
8. Calculate alpha = portfolio_return - benchmark_return
9. Format output (see below)

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

Benchmark Timeline (sampled):
  2025-01-02:  SPY +0.2%
  2025-02-01:  SPY +3.1%
  ...

[DATA_SOURCES: Ghostfolio]
```

### Error Handling
- If get_benchmarks() fails entirely → return error message
- If benchmark symbol not in list → "Benchmark 'X' not available. Available: A, B, C"
- If benchmark detail fails → still show market context section
- If portfolio performance fails → still show benchmark data, skip comparison
- If both benchmark detail + portfolio fail → show just market context

### Tests: Create tests/unit/test_benchmark_comparison.py

Mock the GhostfolioClient with AsyncMock (do NOT use respx — these are tool-level tests, not client tests).

Fixtures:
```python
@pytest.fixture
def mock_client():
    client = AsyncMock(spec=GhostfolioClient)
    # Default benchmark list
    client.get_benchmarks.return_value = {
        "benchmarks": [{
            "dataSource": "YAHOO",
            "symbol": "SPY",
            "name": "S&P 500",
            "marketCondition": "NEUTRAL_MARKET",
            "performances": {
                "allTimeHigh": {
                    "date": "2025-02-19T00:00:00.000Z",
                    "performancePercent": -0.05
                }
            },
            "trend50d": "UP",
            "trend200d": "UP",
        }]
    }
    # Default benchmark detail
    client.get_benchmark_detail.return_value = {
        "marketData": [
            {"date": "2025-01-02", "value": 0},
            {"date": "2025-06-15", "value": 9.8},
        ]
    }
    # Default portfolio performance
    client.get_portfolio_performance.return_value = {
        "performance": {
            "netPerformancePercentage": 0.123,
            "netPerformance": 8450.0,
            "currentNetWorth": 77000.0,
        }
    }
    return client
```

Test cases:
1. test_basic_comparison — all data present, verify output has Market Context + Performance Comparison + Alpha
2. test_default_params — call with no args, verify SPY and ytd used
3. test_custom_benchmark — pass benchmark="QQQ", verify it's used
4. test_benchmark_not_found — symbol not in list, verify "not available" message with available list
5. test_period_ytd_start_date — verify start date is Jan 1 of current year
6. test_period_1y_start_date — verify start date is ~365 days ago
7. test_period_max_start_date — verify start date is 2000-01-01
8. test_benchmark_detail_failure — get_benchmark_detail raises, still shows market context
9. test_portfolio_failure — get_portfolio_performance raises, still shows benchmark data
10. test_both_fail — only market context from benchmarks list
11. test_alpha_positive — portfolio > benchmark → "outperforming"
12. test_alpha_negative — portfolio < benchmark → "underperforming"
13. test_alpha_zero — portfolio == benchmark → "matching"
14. test_data_sources_tag — output ends with [DATA_SOURCES: Ghostfolio]
15. test_market_condition_display — verify NEUTRAL_MARKET → "Neutral Market", BEAR_MARKET → "Bear Market", ALL_TIME_HIGH → "All-Time High"
16. test_timeline_sampling — >20 data points get sampled down
17. test_ath_distance_display — verify ATH % formatted correctly (performancePercent -0.05 → "5.0% from ATH")

Run: uv run pytest tests/unit/test_benchmark_comparison.py -v
All tests must pass.

DO NOT modify __init__.py or graph.py — that will be done separately.
```

---

## Final Wiring Step (after both agents complete)

After both agents finish:

1. Edit `src/ghostfolio_agent/tools/__init__.py`:
   - Import `create_benchmark_comparison_tool`
   - Add to `create_tools()` function

2. Edit `src/ghostfolio_agent/agent/graph.py`:
   - Add benchmark_comparison to SYSTEM_PROMPT Available tools list
   - Add routing rule to Tool routing section:
     ```
     - "am I beating the market?", "compare to S&P", "portfolio vs benchmark", "how's the market?",
       "market trend" → benchmark_comparison ONLY. Do NOT also call portfolio_performance
       (benchmark_comparison already includes portfolio return data).
     - "how did my portfolio do?" (no comparison intent) → portfolio_performance ONLY.
     ```

3. Run full test suite: `uv run pytest tests/unit/ -v`

4. Commit all changes with descriptive message

5. Update MEMORY.md with new tool documentation
