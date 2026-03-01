# Conviction Score — Design Document

**Date:** 2026-02-28
**Feature:** #4 Conviction Score
**Status:** Ready for implementation

## Overview

A composite 0–100 score that quantifies the bullish/bearish signal strength for a given stock symbol. Combines analyst consensus, price target upside, news sentiment, and earnings proximity into a single number with full sub-score transparency.

## Tool Interface

```python
conviction_score(symbol: str) -> str
```

Standalone tool — does not require the holding to be in the user's portfolio. Fetches data from Finnhub, Alpha Vantage, and FMP in parallel.

## Scoring Model

### Components

| Component | Weight | Source | Scoring Logic |
|-----------|--------|--------|---------------|
| Analyst Consensus | 40% | Finnhub `get_analyst_recommendations` | Weighted ratio: `(strongBuy*2 + buy*1 - sell*1 - strongSell*2) / (total*2)` mapped to 0–100. All strong buy = 100, all strong sell = 0 |
| Price Target Upside | 30% | FMP `get_price_target_consensus` + Finnhub `get_quote` | Upside % mapped linearly: +30% or more = 100, -30% or worse = 0, 0% = 50 |
| News Sentiment | 20% | Alpha Vantage `get_news_sentiment` | Bullish article ratio: all bullish = 100, all bearish = 0, mixed = proportional |
| Earnings Proximity | 10% | Finnhub `get_earnings_calendar` | No upcoming earnings = 75 (stable); reporting within 14 days = 50 (uncertainty); just reported is not tracked (data may not be available) |

### Composite Calculation

- Weighted average of all available components
- If a client is unavailable (no API key), its weight redistributes proportionally across remaining components
- Minimum 1 component required; if none available, return an error message

### Label Mapping

| Score Range | Label |
|-------------|-------|
| 0–20 | Strong Sell |
| 21–40 | Sell |
| 41–60 | Neutral |
| 61–80 | Buy |
| 81–100 | Strong Buy |

## Output Format

```
Conviction Score: AAPL (Apple Inc.)

  Score: 74/100 — Buy

  Components:
    Analyst Consensus:   82/100 (weight 40%)  — 18 of 24 analysts bullish
    Price Target Upside: 68/100 (weight 30%)  — +12.4% implied upside ($245.00 target)
    News Sentiment:      71/100 (weight 20%)  — 5 of 7 articles positive
    Earnings Proximity:  50/100 (weight 10%)  — Reporting in 8 days (2026-03-08)

  Data Sources: Finnhub, Alpha Vantage, FMP
  Missing: None
```

When a component is unavailable:
```
    News Sentiment:      N/A (Alpha Vantage not configured)
```

## Integration with holding_detail

The conviction score computation logic lives in `conviction_score.py` as importable functions. The `holding_detail` tool's Smart Summary section will include the composite score as its first line:

```
Smart Summary:
  Conviction Score: 74/100 — Buy
  Implied Upside: +12.4% (target $245.00)
  Analyst Signal: Buy (18 of 24 analysts bullish)
  Sentiment: Bullish (5 of 7 articles positive)
  Earnings Alert: Reporting in 8 days (2026-03-08)
```

The existing Smart Summary signals remain — the conviction score adds a top-line composite without removing the individual signals.

## Implementation

### New file: `src/ghostfolio_agent/tools/conviction_score.py`

- `compute_analyst_score(analyst_data) -> tuple[int, str]` — returns (score, explanation)
- `compute_price_target_score(consensus_data, market_price) -> tuple[int, str]`
- `compute_sentiment_score(news_data) -> tuple[int, str]`
- `compute_earnings_score(earnings_data) -> tuple[int, str]`
- `compute_composite(components: list[tuple[int, str, int]]) -> tuple[int, str, list]` — takes (score, explanation, weight) tuples, returns (composite, label, details)
- `create_conviction_score_tool(finnhub, alpha_vantage, fmp)` — factory function

### Modify: `src/ghostfolio_agent/tools/holding_detail.py`

- Import scoring functions from `conviction_score.py`
- In `_format_smart_summary`, call `compute_composite()` with the enrichment data already fetched
- Prepend "Conviction Score: X/100 — Label" as the first Smart Summary line

### Modify: `src/ghostfolio_agent/agent/graph.py`

- Import `create_conviction_score_tool`
- Add to `create_tools()` list when any enrichment client is configured
- Add system prompt guidance: "Use conviction_score when the user asks about signal strength, conviction, or is evaluating a trade decision on a specific symbol."

### New file: `tests/unit/test_conviction_score.py`

- Test each sub-score function: all bullish, all bearish, mixed, empty data
- Test weight redistribution when 1, 2, or 3 clients missing
- Test composite label mapping at boundaries (20, 40, 60, 80)
- Test full tool output format
- Test graceful degradation with no clients

## Data Flow

```
User: "What's the conviction on AAPL?"
  → Agent calls conviction_score("AAPL")
    → Parallel: finnhub.get_quote("AAPL")
                finnhub.get_analyst_recommendations("AAPL")
                finnhub.get_earnings_calendar("AAPL")
                alpha_vantage.get_news_sentiment("AAPL")
                fmp.get_price_target_consensus("AAPL")
    → Compute 4 sub-scores
    → Weighted composite
    → Return formatted text with score + breakdown
```

## Non-Goals

- No portfolio-wide ranking mode (agent calls tool per symbol if needed)
- No historical score tracking
- No custom weight configuration by user
- No frontend-specific rendering (agent formats in natural language)
