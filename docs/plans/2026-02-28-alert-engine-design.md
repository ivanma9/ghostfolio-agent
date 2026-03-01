# Alert Engine Design

**Date:** 2026-02-28
**Status:** Draft
**Feature:** #6 Alert Engine

## Summary

Proactive alerts that surface automatically when the user sends any message. No background infrastructure — alerts run as a pre-check in the chat flow, prepended to the agent's response. Hardcoded sensible defaults, 24-hour cooldown per alert to prevent fatigue.

## Interaction Model

1. User sends any message
2. Before the agent processes the message, the alert engine runs a quick scan
3. If alerts exist (and haven't fired in the last 24 hours), they're injected into the agent's system context
4. The agent naturally weaves alerts into the start of its response
5. Fired alerts are recorded with timestamps for cooldown tracking

No new frontend components. No WebSocket. No background scheduler.

## Alert Conditions (Hardcoded Defaults)

| Condition | Threshold | Data Source | Description |
|-----------|-----------|-------------|-------------|
| Earnings proximity | ≤ 3 days | Finnhub `get_earnings_calendar` | Holdings reporting earnings soon |
| Big mover | ≥ 5% daily change | Finnhub `get_quote` | Holdings with significant daily price movement |
| Low conviction | < 40 score | Conviction score functions | Holdings where composite conviction score dropped below threshold |
| Analyst downgrade | Consensus shifted to Sell | Finnhub `get_analyst_recommendations` | Holdings where analyst consensus turned bearish |

## Architecture

### Alert Check Flow

```
User message → chat endpoint
  → run_alert_check(holdings, clients)
    → Phase 1: fetch quotes + earnings for all holdings (parallel)
    → Phase 2: for flagged holdings only, fetch analyst + sentiment
    → Filter by cooldown (skip if fired < 24h ago)
    → Return list of alert strings
  → Inject alerts into agent system prompt
  → Agent processes user message normally
```

### Backend

**New file:** `src/ghostfolio_agent/alerts/engine.py`

Core alert engine with:

- `AlertEngine` class holding cooldown state (in-memory dict)
- `async check_alerts(client, finnhub, alpha_vantage, fmp) -> list[str]` — runs the scan
- `COOLDOWN_TTL = 86400` (24 hours)
- Alert key format: `"{condition}:{symbol}"` (e.g. `"earnings:NVDA"`, `"big_mover:TSLA"`)

```python
class AlertEngine:
    def __init__(self):
        self._fired: dict[str, float] = {}  # alert_key -> timestamp

    def _is_cooled_down(self, key: str) -> bool:
        fired_at = self._fired.get(key)
        if fired_at is None:
            return True
        return (time.time() - fired_at) > COOLDOWN_TTL

    def _record(self, key: str):
        self._fired[key] = time.time()
        # Prune old entries
        cutoff = time.time() - COOLDOWN_TTL
        self._fired = {k: v for k, v in self._fired.items() if v > cutoff}

    async def check_alerts(self, client, finnhub, alpha_vantage, fmp) -> list[str]:
        # Fetch holdings
        # Phase 1: parallel quotes + earnings for all symbols
        # Phase 2: analyst data for flagged symbols only
        # Apply cooldown filter
        # Return formatted alert strings
        ...
```

**Two-phase fetch** (same pattern as morning briefing):

- Phase 1: `get_quote` + `get_earnings_calendar` for all holdings (parallel via `asyncio.gather`)
- Phase 2: `get_analyst_recommendations` only for holdings that triggered a Phase 1 flag (big mover or earnings soon) — avoids unnecessary API calls

**Alert evaluation functions:**

```python
def _check_earnings_proximity(symbol, earnings_data, today) -> str | None:
    """Return alert string if earnings within 3 days."""

def _check_big_mover(symbol, quote_data) -> str | None:
    """Return alert string if |daily change| >= 5%."""

def _check_low_conviction(symbol, analyst, pt, news, earnings, market_price) -> str | None:
    """Return alert string if conviction score < 40."""

def _check_analyst_downgrade(symbol, analyst_data) -> str | None:
    """Return alert string if consensus is Sell or Strong Sell."""
```

### Integration Point

**Modified file:** `src/ghostfolio_agent/chat.py`

Before invoking the agent, run alert check and inject results:

```python
# In the chat endpoint, before agent.ainvoke()
alerts = await alert_engine.check_alerts(client, finnhub, alpha_vantage, fmp)

if alerts:
    alert_block = "ALERTS FOR USER:\n" + "\n".join(f"- {a}" for a in alerts)
    # Prepend to the user's message or inject as system context
    # so the agent naturally surfaces them
```

**Modified file:** `src/ghostfolio_agent/agent/graph.py`

The `AlertEngine` instance is created once in the app lifespan (singleton) so cooldown state persists across requests. Passed into the chat handler.

**Modified file:** `src/ghostfolio_agent/main.py`

Instantiate `AlertEngine` at app startup, pass to chat router.

### Rate Limit Awareness

Alpha Vantage (25 req/day) is NOT used in Phase 1. News sentiment is only fetched in Phase 2 for conviction score computation on flagged holdings. With the cooldown preventing re-checks, typical daily usage would be:

- Phase 1: Finnhub only (quotes + earnings) — no rate limit concern
- Phase 2: Runs only for flagged holdings (typically 0-3 per check). Alpha Vantage calls limited to those few symbols.
- Cooldown: Same alert won't re-fetch for 24 hours

Worst case with 10 holdings and all flagged: ~10 Finnhub calls (Phase 1) + ~3 Alpha Vantage + ~3 FMP (Phase 2). Well within limits.

### Cooldown Behavior

- In-memory dict, resets on server restart (acceptable for v1)
- Alert key = `"{condition}:{symbol}"` — so "big_mover:NVDA" and "earnings:NVDA" are tracked independently
- 24-hour TTL with automatic pruning of expired entries
- No persistence needed — if the server restarts, seeing alerts again is fine

## Output Format

Alerts are plain text strings injected into the agent's context. Examples:

```
ALERTS:
- NVDA earnings in 2 days (2026-03-02) — consider position sizing
- TSLA down 6.3% today ($187.42) — significant daily move
- AAPL conviction score dropped to 35/100 (Sell) — review position
- MSFT analyst consensus shifted to Sell (2 of 8 analysts bullish) — monitor closely
```

The agent receives these and naturally mentions them at the start of its response in conversational tone, before addressing whatever the user actually asked.

## Files Changed Summary

### New files (1):
- `src/ghostfolio_agent/alerts/engine.py`
- `src/ghostfolio_agent/alerts/__init__.py`

### Modified files (3):
- `src/ghostfolio_agent/main.py` — instantiate AlertEngine singleton
- `src/ghostfolio_agent/chat.py` — run alert check before agent invocation, inject into context
- `src/ghostfolio_agent/agent/graph.py` — pass alert engine through or accept alert context

### Test file (1):
- `tests/unit/test_alert_engine.py`

## Testing Strategy

Unit tests for:
- Each alert condition function (earnings proximity, big mover, low conviction, analyst downgrade)
- Cooldown logic (fires once, suppressed within 24h, fires again after expiry)
- Phase 1 → Phase 2 gating (only flagged holdings get deep enrichment)
- Graceful degradation (missing clients, API errors)
- Alert formatting

## Future Enhancements (Not in v1)

- User-configurable thresholds ("alert me if any holding drops more than 3%")
- Persistent cooldown state (SQLite or JSON file)
- Separate AlertCard UI component
- WebSocket push for true real-time alerts
