# Morning Briefing — Design Document

**Date:** 2026-02-28
**Feature:** #3 Morning Briefing
**Status:** Ready for implementation

## Overview

A daily portfolio briefing tool that surfaces what matters: top movers, upcoming earnings, sentiment shifts, macro conditions, and actionable flags. Triggered on user request (e.g., "morning briefing", "what's happening today"). Renders as structured cards in the frontend.

Only notable holdings are enriched — top movers and flagged positions — to stay within API rate limits and keep the output actionable.

## Tool Interface

```python
morning_briefing() -> str
```

No arguments. Operates on the user's current portfolio (real or paper, based on active mode).

## Architecture

### Two-Phase Fetch Strategy

**Phase 1: Quick Scan (all holdings, cheap calls)**
- Finnhub `get_quote` for each holding → daily % change → identify top 3 movers
- Finnhub `get_earnings_calendar` for each holding → flag earnings within 7 days
- All calls via `asyncio.gather` in parallel

**Phase 2: Deep Enrichment (notable holdings only)**

A holding is "notable" if it meets any threshold:
- **Top mover**: top 3 by absolute daily % change
- **Earnings soon**: earnings within 7 days
- **Negative sentiment**: Alpha Vantage sentiment score < 0.2
- **Positive sentiment**: Alpha Vantage sentiment score > 0.7
- **Low conviction**: conviction score < 40

For notable holdings, fetch in parallel:
- Alpha Vantage `get_news_sentiment`
- Finnhub `get_analyst_recommendations`
- FMP `get_price_target_consensus`
- Conviction score (reuse existing `compute_conviction_score` functions)

Note: Sentiment thresholds (< 0.2, > 0.7) can only be evaluated after fetching sentiment data. In practice, we fetch sentiment for all top movers and earnings-flagged holdings in Phase 2, then apply sentiment thresholds to determine if additional holdings should be flagged. Holdings that are only notable for sentiment require a broader sentiment scan — to stay within API limits, we limit sentiment checks to Phase 2 holdings only.

### Macro Snapshot with 24-Hour Cache

```python
_macro_cache = {
    "data": None,
    "fetched_at": None
}

MACRO_CACHE_TTL = 86400  # 24 hours
```

- In-memory module-level dict — no Redis, no file storage
- On each briefing: check if `fetched_at` is within TTL, use cached data if so
- Otherwise fetch in parallel: `get_fed_funds_rate()`, `get_cpi()`, `get_treasury_yield("10year")`
- Cache resets on server restart — acceptable since it costs only 3 API calls to rebuild
- Primary value: prevents repeated macro fetches within the same day

### API Budget

Alpha Vantage free tier: 25 requests/day. Worst-case briefing cost:
- ~5 notable holdings × 1 sentiment call = 5 calls
- 3 macro calls (only on first briefing of the day)
- Total: ~5–8 calls per briefing, leaving room for holding_detail and conviction_score usage

## Output Structure

```python
{
    "briefing_date": "2026-02-28",
    "portfolio_overview": {
        "total_value": 52340.50,
        "daily_change": -1.2,
        "daily_change_amount": -635.20,
        "holdings_count": 18
    },
    "top_movers": [
        {
            "symbol": "NVDA",
            "name": "NVIDIA",
            "daily_change": -4.2,
            "current_price": 890.50,
            "direction": "down"
        }
    ],
    "earnings_watch": [
        {
            "symbol": "AAPL",
            "name": "Apple",
            "earnings_date": "2026-03-05",
            "days_until": 5
        }
    ],
    "market_signals": [
        {
            "symbol": "TSLA",
            "name": "Tesla",
            "sentiment_score": 0.15,
            "sentiment_label": "Bearish",
            "analyst_consensus": "Buy",
            "conviction_score": 35,
            "conviction_label": "Sell",
            "flags": ["low_conviction", "negative_sentiment"]
        }
    ],
    "macro_snapshot": {
        "fed_funds_rate": 4.50,
        "cpi": 2.8,
        "treasury_10y": 4.25,
        "cached": true
    },
    "action_items": [
        "TSLA conviction score is 35/100 (Sell) with bearish sentiment — review position",
        "AAPL earnings in 5 days — consider trimming or hedging"
    ]
}
```

## Action Items Generation

Natural language strings summarizing notable flags per holding:

- Low conviction + negative sentiment → "X conviction score is Y/100 (Label) with bearish sentiment — review position"
- Earnings soon → "X earnings in Y days — consider trimming or hedging"
- Big daily drop + low conviction → "X down Z% today with conviction at Y/100 — monitor closely"
- Big daily gain + positive sentiment → "X up Z% today with bullish sentiment — momentum may continue"

## Frontend

### MorningBriefingCard Component

Renders 6 cards vertically, detected via `tool_name === "morning_briefing"` in the message renderer (same pattern as `HoldingDetailCard`).

1. **Portfolio Overview** — total value, daily P&L (green/red), holdings count
2. **Top Movers** — 3 rows: symbol, name, daily % change (green/red)
3. **Earnings Watch** — rows: symbol, earnings date, "in X days" badge (amber accent)
4. **Market Signals** — rows per flagged holding: sentiment label, analyst consensus, conviction badge (red/yellow/green color scheme)
5. **Macro Snapshot** — 3 key-value pairs (fed funds, CPI, 10Y yield), gray/neutral styling, "cached" indicator
6. **Action Items** — bulleted natural language list, amber/warning styling

### Welcome Screen

Add "Morning Briefing" as a suggested prompt on the welcome/landing screen alongside existing suggestions.

### Sidebar Refresh

Trigger sidebar refresh after `morning_briefing` tool call completes (same pattern as `portfolio_summary` and `paper_trade` in `App.tsx`).

## Agent Integration

- Register `morning_briefing` tool in `graph.py`
- No special routing — the LLM naturally handles triggers like "morning briefing", "daily update", "brief me", "what's happening today"

## File Changes

| File | Change |
|------|--------|
| `src/ghostfolio_agent/tools/morning_briefing.py` | New tool + macro cache |
| `src/ghostfolio_agent/agent/graph.py` | Register tool |
| `frontend/src/components/MorningBriefingCard.tsx` | New component |
| `frontend/src/components/ChatMessage.tsx` | Detect and render briefing card |
| `frontend/src/App.tsx` | Sidebar refresh trigger, welcome screen prompt |
| `tests/unit/test_morning_briefing.py` | Unit tests |

## Dependencies

- No new API clients
- No new Python or frontend packages
- Reuses existing Finnhub, Alpha Vantage, FMP clients
- Reuses conviction score computation functions from `tools/conviction_score.py`
