# Morning Briefing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a morning briefing tool that surfaces portfolio overview, top movers, earnings watch, market signals, macro snapshot, and action items as structured cards.

**Architecture:** Two-phase fetch — quick scan all holdings (quotes + earnings), then deep enrich only notable ones (sentiment, analyst, price targets, conviction). Macro data cached 24 hours in-memory. Frontend renders 6 structured cards via `MorningBriefingCard` component.

**Tech Stack:** Python/LangGraph tool, asyncio.gather, existing Finnhub/AlphaVantage/FMP clients, React/Tailwind frontend card

---

### Task 1: Morning Briefing Tool — Helpers and Cache

**Files:**
- Create: `src/ghostfolio_agent/tools/morning_briefing.py`
- Test: `tests/unit/test_morning_briefing.py`

**Step 1: Write tests for macro cache and helper functions**

```python
# tests/unit/test_morning_briefing.py
import pytest
import time
from ghostfolio_agent.tools.morning_briefing import (
    _macro_cache,
    MACRO_CACHE_TTL,
    is_macro_cache_valid,
    generate_action_items,
)


class TestMacroCacheValidity:
    def test_empty_cache_is_invalid(self):
        """Empty cache should be invalid."""
        cache = {"data": None, "fetched_at": None}
        assert is_macro_cache_valid(cache) is False

    def test_fresh_cache_is_valid(self):
        """Cache fetched just now should be valid."""
        cache = {"data": {"fed_funds_rate": 4.5}, "fetched_at": time.time()}
        assert is_macro_cache_valid(cache) is True

    def test_stale_cache_is_invalid(self):
        """Cache older than TTL should be invalid."""
        cache = {"data": {"fed_funds_rate": 4.5}, "fetched_at": time.time() - MACRO_CACHE_TTL - 1}
        assert is_macro_cache_valid(cache) is False


class TestGenerateActionItems:
    def test_low_conviction(self):
        """Low conviction holding generates action item."""
        signals = [
            {
                "symbol": "TSLA",
                "name": "Tesla",
                "conviction_score": 35,
                "conviction_label": "Sell",
                "sentiment_label": "Bearish",
                "flags": ["low_conviction", "negative_sentiment"],
            }
        ]
        items = generate_action_items(signals, [], [])
        assert any("TSLA" in item and "35/100" in item for item in items)

    def test_earnings_soon(self):
        """Upcoming earnings generates action item."""
        earnings = [{"symbol": "AAPL", "name": "Apple", "earnings_date": "2026-03-05", "days_until": 5}]
        items = generate_action_items([], earnings, [])
        assert any("AAPL" in item and "5 days" in item for item in items)

    def test_big_mover_down(self):
        """Large daily drop generates action item."""
        movers = [{"symbol": "NVDA", "name": "NVIDIA", "daily_change": -5.2, "direction": "down"}]
        items = generate_action_items([], [], movers)
        assert any("NVDA" in item and "5.2%" in item for item in items)

    def test_no_flags_no_items(self):
        """No notable flags → empty action items."""
        items = generate_action_items([], [], [])
        assert items == []
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_morning_briefing.py -v`
Expected: FAIL — imports not found

**Step 3: Implement cache helper and action item generator**

```python
# src/ghostfolio_agent/tools/morning_briefing.py
"""Morning Briefing — daily portfolio digest with notable holdings."""

import asyncio
import time
import structlog
from datetime import date
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient
from ghostfolio_agent.tools.conviction_score import (
    compute_analyst_score,
    compute_price_target_score,
    compute_sentiment_score,
    compute_earnings_score,
    compute_composite,
    score_to_label,
    ANALYST_WEIGHT,
    PRICE_TARGET_WEIGHT,
    SENTIMENT_WEIGHT,
    EARNINGS_WEIGHT,
)

logger = structlog.get_logger()

# ── Macro cache ───────────────────────────────────────────────────────────────

MACRO_CACHE_TTL = 86400  # 24 hours in seconds

_macro_cache: dict = {
    "data": None,
    "fetched_at": None,
}


def is_macro_cache_valid(cache: dict) -> bool:
    """Check if macro cache is fresh (within TTL)."""
    if cache["data"] is None or cache["fetched_at"] is None:
        return False
    return (time.time() - cache["fetched_at"]) < MACRO_CACHE_TTL


# ── Action item generation ────────────────────────────────────────────────────


def generate_action_items(
    market_signals: list[dict],
    earnings_watch: list[dict],
    top_movers: list[dict],
) -> list[str]:
    """Generate natural language action items from notable flags."""
    items: list[str] = []

    for signal in market_signals:
        flags = signal.get("flags", [])
        symbol = signal["symbol"]

        if "low_conviction" in flags and "negative_sentiment" in flags:
            items.append(
                f"{symbol} conviction score is {signal['conviction_score']}/100 "
                f"({signal['conviction_label']}) with bearish sentiment — review position"
            )
        elif "low_conviction" in flags:
            items.append(
                f"{symbol} conviction score is {signal['conviction_score']}/100 "
                f"({signal['conviction_label']}) — review position"
            )
        elif "negative_sentiment" in flags:
            items.append(
                f"{symbol} showing bearish sentiment — monitor closely"
            )

    for earning in earnings_watch:
        items.append(
            f"{earning['symbol']} earnings in {earning['days_until']} days — consider position sizing"
        )

    for mover in top_movers:
        if mover["daily_change"] <= -4.0:
            items.append(
                f"{mover['symbol']} down {abs(mover['daily_change']):.1f}% today — monitor closely"
            )
        elif mover["daily_change"] >= 4.0:
            items.append(
                f"{mover['symbol']} up {mover['daily_change']:.1f}% today — momentum may continue"
            )

    return items
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_morning_briefing.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/tools/morning_briefing.py tests/unit/test_morning_briefing.py
git commit -m "feat(morning-briefing): add macro cache and action item helpers with tests"
```

---

### Task 2: Morning Briefing Tool — Two-Phase Fetch and Tool Function

**Files:**
- Modify: `src/ghostfolio_agent/tools/morning_briefing.py`
- Test: `tests/unit/test_morning_briefing.py`

**Step 1: Write integration tests for the full tool**

Add to `tests/unit/test_morning_briefing.py`:

```python
from unittest.mock import MagicMock, AsyncMock


# ── Mock data ─────────────────────────────────────────────────────────────────

HOLDINGS_RESPONSE = {
    "holdings": {
        "AAPL": {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "quantity": 10,
            "marketPrice": 200.0,
            "valueInBaseCurrency": 2000.0,
            "allocationInPercentage": 0.4,
        },
        "NVDA": {
            "symbol": "NVDA",
            "name": "NVIDIA Corp",
            "quantity": 5,
            "marketPrice": 900.0,
            "valueInBaseCurrency": 4500.0,
            "allocationInPercentage": 0.45,
        },
        "MSFT": {
            "symbol": "MSFT",
            "name": "Microsoft Corp",
            "quantity": 8,
            "marketPrice": 400.0,
            "valueInBaseCurrency": 3200.0,
            "allocationInPercentage": 0.15,
        },
    }
}

QUOTE_AAPL = {"c": 200.0, "dp": -5.0, "d": -10.0}  # down 5%
QUOTE_NVDA = {"c": 900.0, "dp": 3.2, "d": 28.8}    # up 3.2%
QUOTE_MSFT = {"c": 400.0, "dp": 0.5, "d": 2.0}     # flat

EARNINGS_AAPL = [{"date": "2026-03-05", "epsEstimate": 2.1, "epsActual": None, "symbol": "AAPL"}]
EARNINGS_NVDA = []
EARNINGS_MSFT = []

ANALYST_AAPL = [{"strongBuy": 10, "buy": 15, "hold": 5, "sell": 1, "strongSell": 0, "period": "2026-02-01"}]

NEWS_AAPL = [
    {"overall_sentiment_label": "Bearish", "title": "Apple faces headwinds", "source": "Reuters"},
    {"overall_sentiment_label": "Somewhat_Bearish", "title": "Apple warns on supply", "source": "Bloomberg"},
]

PT_CONSENSUS_AAPL = [{"targetConsensus": 230.0, "targetHigh": 280.0, "targetLow": 180.0}]

MACRO_FED = {"data": [{"date": "2026-01-29", "value": "4.50"}]}
MACRO_CPI = {"data": [{"date": "2026-01-15", "value": "2.80"}]}
MACRO_TREASURY = {"data": [{"date": "2026-02-27", "value": "4.25"}]}


@pytest.fixture
def ghostfolio_client():
    client = MagicMock(spec=GhostfolioClient)
    client.get_portfolio_holdings = AsyncMock(return_value=HOLDINGS_RESPONSE)
    return client


@pytest.fixture
def finnhub_client():
    client = MagicMock(spec=FinnhubClient)

    async def mock_quote(symbol):
        return {"AAPL": QUOTE_AAPL, "NVDA": QUOTE_NVDA, "MSFT": QUOTE_MSFT}.get(symbol, {"c": 0, "dp": 0, "d": 0})

    async def mock_earnings(symbol):
        return {"AAPL": EARNINGS_AAPL, "NVDA": EARNINGS_NVDA, "MSFT": EARNINGS_MSFT}.get(symbol, [])

    async def mock_analyst(symbol):
        return {"AAPL": ANALYST_AAPL}.get(symbol, [])

    client.get_quote = MagicMock(side_effect=mock_quote)
    client.get_earnings_calendar = MagicMock(side_effect=mock_earnings)
    client.get_analyst_recommendations = MagicMock(side_effect=mock_analyst)
    return client


@pytest.fixture
def alpha_vantage_client():
    client = MagicMock(spec=AlphaVantageClient)

    async def mock_news(ticker):
        return {"AAPL": NEWS_AAPL}.get(ticker, [])

    async def mock_fed():
        return MACRO_FED

    async def mock_cpi():
        return MACRO_CPI

    async def mock_treasury(maturity="10year"):
        return MACRO_TREASURY

    client.get_news_sentiment = MagicMock(side_effect=mock_news)
    client.get_fed_funds_rate = MagicMock(side_effect=mock_fed)
    client.get_cpi = MagicMock(side_effect=mock_cpi)
    client.get_treasury_yield = MagicMock(side_effect=mock_treasury)
    return client


@pytest.fixture
def fmp_client():
    client = MagicMock(spec=FMPClient)

    async def mock_pt(symbol):
        return {"AAPL": PT_CONSENSUS_AAPL}.get(symbol, [])

    client.get_price_target_consensus = MagicMock(side_effect=mock_pt)
    return client


class TestMorningBriefingTool:
    @pytest.mark.asyncio
    async def test_full_briefing(self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client):
        """Full briefing includes all 6 sections."""
        from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool, _macro_cache

        # Reset macro cache
        _macro_cache["data"] = None
        _macro_cache["fetched_at"] = None

        tool = create_morning_briefing_tool(
            ghostfolio_client, finnhub=finnhub_client, alpha_vantage=alpha_vantage_client, fmp=fmp_client
        )
        result = await tool.ainvoke({})

        # Portfolio overview
        assert "Portfolio Overview" in result
        assert "$9,700.00" in result  # 2000 + 4500 + 3200

        # Top movers — AAPL should be top mover (down 5%)
        assert "Top Movers" in result
        assert "AAPL" in result

        # Earnings watch — AAPL has earnings in ~5 days
        assert "Earnings Watch" in result

        # Market signals
        assert "Market Signals" in result

        # Macro snapshot
        assert "Macro Snapshot" in result
        assert "4.50" in result  # fed funds
        assert "2.80" in result  # CPI

        # Action items
        assert "Action Items" in result

    @pytest.mark.asyncio
    async def test_empty_portfolio(self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client):
        """Empty portfolio returns a helpful message."""
        from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool

        ghostfolio_client.get_portfolio_holdings = AsyncMock(return_value={"holdings": {}})
        tool = create_morning_briefing_tool(
            ghostfolio_client, finnhub=finnhub_client, alpha_vantage=alpha_vantage_client, fmp=fmp_client
        )
        result = await tool.ainvoke({})
        assert "no holdings" in result.lower()

    @pytest.mark.asyncio
    async def test_no_external_clients(self, ghostfolio_client):
        """Briefing works with only Ghostfolio client (degraded)."""
        from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool

        tool = create_morning_briefing_tool(ghostfolio_client)
        result = await tool.ainvoke({})
        assert "Portfolio Overview" in result

    @pytest.mark.asyncio
    async def test_macro_cache_used_on_second_call(self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client):
        """Second briefing call reuses cached macro data."""
        from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool, _macro_cache

        _macro_cache["data"] = None
        _macro_cache["fetched_at"] = None

        tool = create_morning_briefing_tool(
            ghostfolio_client, finnhub=finnhub_client, alpha_vantage=alpha_vantage_client, fmp=fmp_client
        )
        await tool.ainvoke({})

        # Reset call counts for macro endpoints
        alpha_vantage_client.get_fed_funds_rate.reset_mock()
        alpha_vantage_client.get_cpi.reset_mock()
        alpha_vantage_client.get_treasury_yield.reset_mock()

        await tool.ainvoke({})

        # Macro endpoints should NOT have been called again
        alpha_vantage_client.get_fed_funds_rate.assert_not_called()
        alpha_vantage_client.get_cpi.assert_not_called()
        alpha_vantage_client.get_treasury_yield.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_morning_briefing.py::TestMorningBriefingTool -v`
Expected: FAIL — `create_morning_briefing_tool` not found

**Step 3: Implement the full tool function**

Add to `src/ghostfolio_agent/tools/morning_briefing.py` after the existing code:

```python
async def _safe_fetch(coro, label: str):
    """Run a coroutine and return None on any exception."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("briefing_fetch_failed", label=label, error=str(exc))
        return None


async def _fetch_macro(alpha_vantage: AlphaVantageClient | None) -> dict:
    """Fetch macro data, using cache if valid."""
    global _macro_cache

    if is_macro_cache_valid(_macro_cache):
        return {**_macro_cache["data"], "cached": True}

    if not alpha_vantage:
        return {}

    fed, cpi, treasury = await asyncio.gather(
        _safe_fetch(alpha_vantage.get_fed_funds_rate(), "fed_funds"),
        _safe_fetch(alpha_vantage.get_cpi(), "cpi"),
        _safe_fetch(alpha_vantage.get_treasury_yield("10year"), "treasury"),
    )

    data = {}
    if fed and fed.get("data"):
        data["fed_funds_rate"] = fed["data"][0].get("value", "N/A")
    if cpi and cpi.get("data"):
        data["cpi"] = cpi["data"][0].get("value", "N/A")
    if treasury and treasury.get("data"):
        data["treasury_10y"] = treasury["data"][0].get("value", "N/A")

    _macro_cache["data"] = data
    _macro_cache["fetched_at"] = time.time()

    return {**data, "cached": False}


def create_morning_briefing_tool(
    client: GhostfolioClient,
    finnhub: FinnhubClient | None = None,
    alpha_vantage: AlphaVantageClient | None = None,
    fmp: FMPClient | None = None,
):
    @tool
    async def morning_briefing() -> str:
        """Get a daily morning briefing with portfolio overview, top movers, upcoming earnings,
        market signals, macro snapshot, and action items. Use when the user asks for a morning
        briefing, daily update, or wants to know what's happening today with their portfolio."""

        # ── Fetch portfolio holdings ──────────────────────────────────────────
        try:
            data = await client.get_portfolio_holdings()
        except Exception as e:
            logger.error("briefing_holdings_failed", error=str(e))
            return "Sorry, I couldn't fetch your portfolio data for the morning briefing."

        raw_holdings = data.get("holdings", {})
        if isinstance(raw_holdings, dict):
            holdings = list(raw_holdings.values())
        else:
            holdings = list(raw_holdings)

        if not holdings:
            return "Your portfolio has no holdings — nothing to brief on."

        # ── Phase 1: Quick scan — quotes + earnings for all holdings ──────────
        symbols = [h.get("symbol", "") for h in holdings if h.get("symbol")]
        total_value = sum(h.get("valueInBaseCurrency", 0) or 0 for h in holdings)

        # Parallel quote + earnings fetch
        quote_tasks = []
        earnings_tasks = []
        for sym in symbols:
            if finnhub:
                quote_tasks.append(_safe_fetch(finnhub.get_quote(sym), f"quote_{sym}"))
                earnings_tasks.append(_safe_fetch(finnhub.get_earnings_calendar(sym), f"earnings_{sym}"))
            else:
                quote_tasks.append(asyncio.coroutine(lambda: None)())
                earnings_tasks.append(asyncio.coroutine(lambda: None)())

        all_tasks = quote_tasks + earnings_tasks
        results = await asyncio.gather(*all_tasks) if all_tasks else []

        quotes = dict(zip(symbols, results[: len(symbols)]))
        earnings_data = dict(zip(symbols, results[len(symbols) :]))

        # Build holdings map for name lookups
        holdings_map = {}
        for h in holdings:
            sym = h.get("symbol", "")
            holdings_map[sym] = h

        # Compute daily change per holding
        daily_changes = {}
        for sym in symbols:
            q = quotes.get(sym)
            if q:
                daily_changes[sym] = q.get("dp", 0) or 0
            else:
                daily_changes[sym] = 0

        # Top 3 movers by absolute change
        sorted_movers = sorted(symbols, key=lambda s: abs(daily_changes.get(s, 0)), reverse=True)
        top_mover_symbols = sorted_movers[:3]

        top_movers = []
        for sym in top_mover_symbols:
            change = daily_changes[sym]
            if change == 0:
                continue
            q = quotes.get(sym, {})
            top_movers.append({
                "symbol": sym,
                "name": holdings_map.get(sym, {}).get("name", sym),
                "daily_change": round(change, 2),
                "current_price": q.get("c", 0) if q else 0,
                "direction": "up" if change > 0 else "down",
            })

        # Daily portfolio change
        daily_change_amount = sum(
            (quotes.get(sym, {}).get("d", 0) or 0) * (holdings_map.get(sym, {}).get("quantity", 0) or 0)
            for sym in symbols
        )
        daily_change_pct = (daily_change_amount / total_value * 100) if total_value > 0 else 0

        # Earnings within 7 days
        today = date.today()
        earnings_watch = []
        earnings_flagged_symbols = set()
        for sym in symbols:
            entries = earnings_data.get(sym) or []
            for entry in entries:
                date_str = entry.get("date", "")
                try:
                    edate = date.fromisoformat(date_str)
                    days_until = (edate - today).days
                    if 0 <= days_until <= 7:
                        earnings_watch.append({
                            "symbol": sym,
                            "name": holdings_map.get(sym, {}).get("name", sym),
                            "earnings_date": date_str,
                            "days_until": days_until,
                        })
                        earnings_flagged_symbols.add(sym)
                except (ValueError, TypeError):
                    continue

        # ── Phase 2: Deep enrichment for notable holdings ─────────────────────
        notable_symbols = set(top_mover_symbols) | earnings_flagged_symbols

        market_signals = []
        if notable_symbols and (alpha_vantage or finnhub or fmp):
            enrich_tasks = {}
            for sym in notable_symbols:
                sym_tasks = {}
                if alpha_vantage:
                    sym_tasks["news"] = _safe_fetch(alpha_vantage.get_news_sentiment(sym), f"news_{sym}")
                if finnhub:
                    sym_tasks["analyst"] = _safe_fetch(finnhub.get_analyst_recommendations(sym), f"analyst_{sym}")
                if fmp:
                    sym_tasks["pt"] = _safe_fetch(fmp.get_price_target_consensus(sym), f"pt_{sym}")
                enrich_tasks[sym] = sym_tasks

            # Flatten and gather
            flat_keys = []
            flat_coros = []
            for sym, tasks in enrich_tasks.items():
                for key, coro in tasks.items():
                    flat_keys.append((sym, key))
                    flat_coros.append(coro)

            flat_results = await asyncio.gather(*flat_coros) if flat_coros else []

            # Reassemble per-symbol
            enriched = {sym: {} for sym in notable_symbols}
            for (sym, key), result in zip(flat_keys, flat_results):
                enriched[sym][key] = result

            # Build market signals with conviction scores
            for sym in notable_symbols:
                sym_data = enriched[sym]
                q = quotes.get(sym, {})
                market_price = q.get("c", 0) if q else 0

                # Compute conviction sub-scores
                components = []
                analyst_score, analyst_expl = compute_analyst_score(sym_data.get("analyst"))
                if analyst_score is not None:
                    components.append(("analyst", analyst_score, analyst_expl, ANALYST_WEIGHT))

                pt_score, pt_expl = compute_price_target_score(sym_data.get("pt"), market_price)
                if pt_score is not None:
                    components.append(("price_target", pt_score, pt_expl, PRICE_TARGET_WEIGHT))

                sent_score, sent_expl = compute_sentiment_score(sym_data.get("news"))
                if sent_score is not None:
                    components.append(("sentiment", sent_score, sent_expl, SENTIMENT_WEIGHT))

                earn_score, earn_expl = compute_earnings_score(earnings_data.get(sym))
                components.append(("earnings", earn_score, earn_expl, EARNINGS_WEIGHT))

                composite, label, _ = compute_composite(components)

                # Determine sentiment label
                sentiment_label = "Neutral"
                if sym_data.get("news"):
                    bullish_labels = {"Bullish", "Somewhat_Bullish", "Somewhat-Bullish"}
                    bearish_labels = {"Bearish", "Somewhat_Bearish", "Somewhat-Bearish"}
                    articles = sym_data["news"]
                    bullish_count = sum(1 for a in articles if a.get("overall_sentiment_label") in bullish_labels)
                    bearish_count = sum(1 for a in articles if a.get("overall_sentiment_label") in bearish_labels)
                    if bearish_count > bullish_count:
                        sentiment_label = "Bearish"
                    elif bullish_count > bearish_count:
                        sentiment_label = "Bullish"

                # Determine analyst consensus label
                analyst_consensus = "N/A"
                analyst_data = sym_data.get("analyst")
                if analyst_data and len(analyst_data) > 0:
                    entry = analyst_data[0]
                    total_analysts = sum(entry.get(k, 0) for k in ["strongBuy", "buy", "hold", "sell", "strongSell"])
                    bullish = entry.get("strongBuy", 0) + entry.get("buy", 0)
                    if total_analysts > 0:
                        ratio = bullish / total_analysts
                        if ratio >= 0.7:
                            analyst_consensus = "Strong Buy"
                        elif ratio >= 0.5:
                            analyst_consensus = "Buy"
                        elif ratio >= 0.3:
                            analyst_consensus = "Hold"
                        else:
                            analyst_consensus = "Sell"

                # Determine flags
                flags = []
                if composite is not None and composite < 40:
                    flags.append("low_conviction")
                if sentiment_label == "Bearish":
                    flags.append("negative_sentiment")
                if sentiment_label == "Bullish":
                    flags.append("positive_sentiment")

                signal = {
                    "symbol": sym,
                    "name": holdings_map.get(sym, {}).get("name", sym),
                    "sentiment_score": sent_score,
                    "sentiment_label": sentiment_label,
                    "analyst_consensus": analyst_consensus,
                    "conviction_score": composite,
                    "conviction_label": label if composite is not None else "N/A",
                    "flags": flags,
                }
                market_signals.append(signal)

        # ── Macro snapshot ────────────────────────────────────────────────────
        macro = await _fetch_macro(alpha_vantage)

        # ── Action items ──────────────────────────────────────────────────────
        action_items = generate_action_items(market_signals, earnings_watch, top_movers)

        # ── Format output ─────────────────────────────────────────────────────
        lines = [
            f"Morning Briefing: {today.strftime('%B %d, %Y')}",
            "",
            "Portfolio Overview:",
            f"  Total Value: ${total_value:,.2f}",
            f"  Daily Change: {daily_change_pct:+.1f}% (${daily_change_amount:+,.2f})",
            f"  Holdings: {len(holdings)}",
            "",
        ]

        lines.append("Top Movers:")
        if top_movers:
            for m in top_movers:
                arrow = "▲" if m["direction"] == "up" else "▼"
                lines.append(
                    f"  {arrow} {m['symbol']} ({m['name']}): {m['daily_change']:+.1f}% @ ${m['current_price']:,.2f}"
                )
        else:
            lines.append("  No significant movers today")
        lines.append("")

        lines.append("Earnings Watch:")
        if earnings_watch:
            for e in earnings_watch:
                lines.append(f"  {e['symbol']} ({e['name']}): {e['earnings_date']} (in {e['days_until']} days)")
        else:
            lines.append("  No upcoming earnings this week")
        lines.append("")

        lines.append("Market Signals:")
        if market_signals:
            for s in market_signals:
                conv_str = f"{s['conviction_score']}/100 ({s['conviction_label']})" if s["conviction_score"] is not None else "N/A"
                lines.append(
                    f"  {s['symbol']} ({s['name']}): Sentiment={s['sentiment_label']}, "
                    f"Analyst={s['analyst_consensus']}, Conviction={conv_str}"
                )
                if s["flags"]:
                    lines.append(f"    Flags: {', '.join(s['flags'])}")
        else:
            lines.append("  No notable signals")
        lines.append("")

        lines.append("Macro Snapshot:")
        if macro:
            fed = macro.get("fed_funds_rate", "N/A")
            cpi_val = macro.get("cpi", "N/A")
            treasury = macro.get("treasury_10y", "N/A")
            cached_str = " (cached)" if macro.get("cached") else ""
            lines.append(f"  Fed Funds Rate: {fed}%{cached_str}")
            lines.append(f"  CPI: {cpi_val}%")
            lines.append(f"  10Y Treasury Yield: {treasury}%")
        else:
            lines.append("  Macro data not available")
        lines.append("")

        lines.append("Action Items:")
        if action_items:
            for item in action_items:
                lines.append(f"  • {item}")
        else:
            lines.append("  No action items — portfolio looks stable")

        return "\n".join(lines)

    return morning_briefing
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_morning_briefing.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/tools/morning_briefing.py tests/unit/test_morning_briefing.py
git commit -m "feat(morning-briefing): implement two-phase fetch tool with full briefing output"
```

---

### Task 3: Register Tool in Agent

**Files:**
- Modify: `src/ghostfolio_agent/tools/__init__.py`
- Modify: `src/ghostfolio_agent/agent/graph.py`

**Step 1: Add import and registration in `__init__.py`**

In `src/ghostfolio_agent/tools/__init__.py`, add the import after the conviction_score import (line 14):

```python
from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool
```

Add to the `tools` list inside `create_tools()` (after the conviction_score line):

```python
        create_morning_briefing_tool(client, finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp),
```

**Step 2: Add tool description to SYSTEM_PROMPT in `graph.py`**

In `src/ghostfolio_agent/agent/graph.py`, add after the conviction_score line in the SYSTEM_PROMPT (after line 34):

```
- morning_briefing: Get a daily morning briefing — portfolio overview, top movers, upcoming earnings, market signals, macro snapshot, and action items. Use when the user asks for a morning briefing, daily update, or wants to know what's happening today.
```

**Step 3: Run all tests**

Run: `uv run pytest tests/unit/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/ghostfolio_agent/tools/__init__.py src/ghostfolio_agent/agent/graph.py
git commit -m "feat(morning-briefing): register tool in agent graph and system prompt"
```

---

### Task 4: Frontend — Parser and Types

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/Chat/RichCard.tsx`

**Step 1: Add TypeScript types**

Add to `frontend/src/types/index.ts`:

```typescript
export interface MorningBriefingData {
  briefingDate: string
  portfolioOverview: {
    totalValue: number
    dailyChange: number
    dailyChangeAmount: number
    holdingsCount: number
  }
  topMovers: Array<{
    symbol: string
    name: string
    dailyChange: number
    currentPrice: number
    direction: 'up' | 'down'
  }>
  earningsWatch: Array<{
    symbol: string
    name: string
    earningsDate: string
    daysUntil: number
  }>
  marketSignals: Array<{
    symbol: string
    name: string
    sentimentLabel: string
    analystConsensus: string
    convictionScore: number | null
    convictionLabel: string
    flags: string[]
  }>
  macroSnapshot: {
    fedFundsRate: string
    cpi: string
    treasury10y: string
    cached: boolean
  }
  actionItems: string[]
}
```

**Step 2: Add parser in `RichCard.tsx`**

Add the `parseMorningBriefing` function after the existing parsers (before the card components section, around line 370):

```typescript
function parseMorningBriefing(text: string): MorningBriefingData | null {
  if (!text.includes('Morning Briefing:')) return null

  // Date
  const dateMatch = text.match(/Morning Briefing:\s*(.+)/)
  const briefingDate = dateMatch?.[1]?.trim() || new Date().toLocaleDateString()

  // Portfolio Overview
  const totalValueMatch = text.match(/Total Value:\s*\$([\d,]+\.?\d*)/)
  const dailyChangeMatch = text.match(/Daily Change:\s*([+-]?[\d.]+)%\s*\(\$([+-]?[\d,.]+)\)/)
  const holdingsCountMatch = text.match(/Holdings:\s*(\d+)/)

  const portfolioOverview = {
    totalValue: totalValueMatch ? parseFloat(totalValueMatch[1].replace(/,/g, '')) : 0,
    dailyChange: dailyChangeMatch ? parseFloat(dailyChangeMatch[1]) : 0,
    dailyChangeAmount: dailyChangeMatch ? parseFloat(dailyChangeMatch[2].replace(/,/g, '')) : 0,
    holdingsCount: holdingsCountMatch ? parseInt(holdingsCountMatch[1]) : 0,
  }

  // Top Movers
  const topMovers: MorningBriefingData['topMovers'] = []
  const moverRegex = /[▲▼]\s+(\w+)\s+\(([^)]+)\):\s*([+-]?[\d.]+)%\s*@\s*\$([\d,]+\.?\d*)/g
  let match
  while ((match = moverRegex.exec(text)) !== null) {
    topMovers.push({
      symbol: match[1],
      name: match[2],
      dailyChange: parseFloat(match[3]),
      currentPrice: parseFloat(match[4].replace(/,/g, '')),
      direction: match[3].startsWith('-') ? 'down' : 'up',
    })
  }

  // Earnings Watch
  const earningsWatch: MorningBriefingData['earningsWatch'] = []
  const earningsRegex = /(\w+)\s+\(([^)]+)\):\s*(\d{4}-\d{2}-\d{2})\s*\(in\s+(\d+)\s+days?\)/g
  while ((match = earningsRegex.exec(text)) !== null) {
    earningsWatch.push({
      symbol: match[1],
      name: match[2],
      earningsDate: match[3],
      daysUntil: parseInt(match[4]),
    })
  }

  // Market Signals
  const marketSignals: MorningBriefingData['marketSignals'] = []
  const signalRegex = /(\w+)\s+\(([^)]+)\):\s*Sentiment=(\w+),\s*Analyst=([^,]+),\s*Conviction=(?:(\d+)\/100\s*\(([^)]+)\)|N\/A)/g
  while ((match = signalRegex.exec(text)) !== null) {
    const flagsMatch = text.slice(match.index).match(/Flags:\s*(.+)/)
    const flags = flagsMatch ? flagsMatch[1].split(',').map((f: string) => f.trim()) : []
    marketSignals.push({
      symbol: match[1],
      name: match[2],
      sentimentLabel: match[3],
      analystConsensus: match[4].trim(),
      convictionScore: match[5] ? parseInt(match[5]) : null,
      convictionLabel: match[6] || 'N/A',
      flags,
    })
  }

  // Macro Snapshot
  const fedMatch = text.match(/Fed Funds Rate:\s*([\d.]+)%/)
  const cpiMatch = text.match(/CPI:\s*([\d.]+)%/)
  const treasuryMatch = text.match(/10Y Treasury Yield:\s*([\d.]+)%/)
  const cachedMatch = text.includes('(cached)')
  const macroSnapshot = {
    fedFundsRate: fedMatch?.[1] || 'N/A',
    cpi: cpiMatch?.[1] || 'N/A',
    treasury10y: treasuryMatch?.[1] || 'N/A',
    cached: cachedMatch,
  }

  // Action Items
  const actionItems: string[] = []
  const actionRegex = /•\s+(.+)/g
  while ((match = actionRegex.exec(text)) !== null) {
    actionItems.push(match[1].trim())
  }

  return {
    briefingDate,
    portfolioOverview,
    topMovers,
    earningsWatch,
    marketSignals,
    macroSnapshot,
    actionItems,
  }
}
```

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/Chat/RichCard.tsx
git commit -m "feat(morning-briefing): add TypeScript types and text parser"
```

---

### Task 5: Frontend — MorningBriefingCard Component

**Files:**
- Modify: `frontend/src/components/Chat/RichCard.tsx`

**Step 1: Add `MorningBriefingCard` component**

Add the component after the existing card components (before the main export dispatcher):

```typescript
function MorningBriefingCard({ data }: { data: MorningBriefingData }) {
  const isPositive = data.portfolioOverview.dailyChange >= 0
  const changeColor = isPositive ? 'text-emerald-600' : 'text-red-500'
  const changeBg = isPositive ? 'bg-emerald-50' : 'bg-red-50'

  return (
    <div className="mt-3 space-y-3">
      {/* Portfolio Overview */}
      <div className="bg-gradient-to-r from-indigo-50 to-violet-50 rounded-xl p-4 border border-indigo-100">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-indigo-900">Portfolio Overview</h3>
          <span className="text-xs text-indigo-500">{data.briefingDate}</span>
        </div>
        <div className="text-2xl font-bold text-gray-900">
          ${data.portfolioOverview.totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <span className={`text-sm font-semibold ${changeColor}`}>
            {data.portfolioOverview.dailyChange >= 0 ? '+' : ''}{data.portfolioOverview.dailyChange.toFixed(1)}%
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${changeBg} ${changeColor}`}>
            ${data.portfolioOverview.dailyChangeAmount >= 0 ? '+' : ''}{data.portfolioOverview.dailyChangeAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span className="text-xs text-gray-500">{data.portfolioOverview.holdingsCount} holdings</span>
        </div>
      </div>

      {/* Top Movers */}
      {data.topMovers.length > 0 && (
        <div className="bg-white rounded-xl p-4 border border-gray-200">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Top Movers</h3>
          <div className="space-y-2">
            {data.topMovers.map((m) => (
              <div key={m.symbol} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`text-lg ${m.direction === 'up' ? 'text-emerald-500' : 'text-red-500'}`}>
                    {m.direction === 'up' ? '▲' : '▼'}
                  </span>
                  <div>
                    <span className="font-semibold text-sm text-gray-900">{m.symbol}</span>
                    <span className="text-xs text-gray-500 ml-1">{m.name}</span>
                  </div>
                </div>
                <div className="text-right">
                  <span className={`text-sm font-semibold ${m.direction === 'up' ? 'text-emerald-600' : 'text-red-500'}`}>
                    {m.dailyChange >= 0 ? '+' : ''}{m.dailyChange.toFixed(1)}%
                  </span>
                  <span className="text-xs text-gray-500 ml-2">${m.currentPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Earnings Watch */}
      {data.earningsWatch.length > 0 && (
        <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
          <h3 className="text-sm font-semibold text-amber-800 mb-2">Earnings Watch</h3>
          <div className="space-y-2">
            {data.earningsWatch.map((e) => (
              <div key={e.symbol} className="flex items-center justify-between">
                <div>
                  <span className="font-semibold text-sm text-gray-900">{e.symbol}</span>
                  <span className="text-xs text-gray-600 ml-1">{e.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-600">{e.earningsDate}</span>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-200 text-amber-800">
                    in {e.daysUntil} days
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Market Signals */}
      {data.marketSignals.length > 0 && (
        <div className="bg-white rounded-xl p-4 border border-gray-200">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Market Signals</h3>
          <div className="space-y-3">
            {data.marketSignals.map((s) => (
              <div key={s.symbol} className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm text-gray-900">{s.symbol}</span>
                  <span className="text-xs text-gray-500">{s.name}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    s.sentimentLabel === 'Bullish' ? 'bg-emerald-100 text-emerald-700' :
                    s.sentimentLabel === 'Bearish' ? 'bg-red-100 text-red-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {s.sentimentLabel}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
                    {s.analystConsensus}
                  </span>
                  {s.convictionScore !== null && (
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      s.convictionScore >= 61 ? 'bg-emerald-100 text-emerald-700' :
                      s.convictionScore >= 41 ? 'bg-yellow-100 text-yellow-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {s.convictionScore}/100 {s.convictionLabel}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Macro Snapshot */}
      {(data.macroSnapshot.fedFundsRate !== 'N/A' || data.macroSnapshot.cpi !== 'N/A') && (
        <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-600">Macro Snapshot</h3>
            {data.macroSnapshot.cached && (
              <span className="text-[10px] text-gray-400 uppercase tracking-wider">cached</span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <div className="text-xs text-gray-500">Fed Funds</div>
              <div className="text-sm font-semibold text-gray-800">{data.macroSnapshot.fedFundsRate}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">CPI</div>
              <div className="text-sm font-semibold text-gray-800">{data.macroSnapshot.cpi}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">10Y Treasury</div>
              <div className="text-sm font-semibold text-gray-800">{data.macroSnapshot.treasury10y}%</div>
            </div>
          </div>
        </div>
      )}

      {/* Action Items */}
      {data.actionItems.length > 0 && (
        <div className="bg-amber-50 rounded-xl p-4 border border-amber-300">
          <h3 className="text-sm font-semibold text-amber-800 mb-2">Action Items</h3>
          <ul className="space-y-1.5">
            {data.actionItems.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-amber-900">
                <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
```

**Step 2: Add to the RichCard dispatcher**

In the `RichCard` default export, add before the `return null` at the end:

```typescript
  if (toolCalls.includes('morning_briefing')) {
    const data = parseMorningBriefing(content)
    if (data) return <MorningBriefingCard data={data} />
  }
```

**Step 3: Add the type import at the top of RichCard.tsx**

Add `MorningBriefingData` to the imports from `../../types`.

**Step 4: Commit**

```bash
git add frontend/src/components/Chat/RichCard.tsx
git commit -m "feat(morning-briefing): add MorningBriefingCard component and dispatcher"
```

---

### Task 6: Frontend — Strip Rules, Welcome Prompt, Sidebar Refresh

**Files:**
- Modify: `frontend/src/components/Chat/MessageBubble.tsx`
- Modify: `frontend/src/components/Chat/ChatPanel.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Add strip rules in `MessageBubble.tsx`**

In the `stripRawData` function, add a new block after the `paper_trade` block (before `return true`):

```typescript
    // Strip raw morning briefing data lines when RichCard renders them
    if (toolCalls.includes('morning_briefing')) {
      if (/^\s*(Total Value:|Daily Change:|Holdings:)\s/i.test(trimmed)) return false
      if (/^\s*[▲▼]\s+\w+/.test(trimmed)) return false
      if (/^\s*(Fed Funds Rate:|CPI:|10Y Treasury Yield:)\s/i.test(trimmed)) return false
      if (/^\s*•\s+/.test(trimmed)) return false
      if (/^\s*(Portfolio Overview|Top Movers|Earnings Watch|Market Signals|Macro Snapshot|Action Items):?\s*$/i.test(trimmed)) return false
      if (/^\s*Sentiment=/.test(trimmed)) return false
      if (/^\s*Flags:/.test(trimmed)) return false
      if (/^\s*\w+\s+\([^)]+\):\s*(Sentiment=|\d{4}-\d{2}-\d{2}\s*\(in)/.test(trimmed)) return false
    }
```

**Step 2: Add suggested prompt in `ChatPanel.tsx`**

Change `SUGGESTED_QUERIES` to include "Morning Briefing":

```typescript
const SUGGESTED_QUERIES = [
  'Morning Briefing',
  "What's in my portfolio?",
  'Show my recent transactions',
]
```

**Step 3: Add sidebar refresh trigger in `App.tsx`**

In the `handleToolCall` callback, update the condition:

```typescript
      if (toolCalls.includes('portfolio_summary') || toolCalls.includes('paper_trade') || toolCalls.includes('morning_briefing')) {
        sidebar.refresh()
      }
```

**Step 4: Run all tests**

Run: `uv run pytest tests/unit/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add frontend/src/components/Chat/MessageBubble.tsx frontend/src/components/Chat/ChatPanel.tsx frontend/src/App.tsx
git commit -m "feat(morning-briefing): add strip rules, welcome prompt, and sidebar refresh"
```

---

### Task 7: Run Full Test Suite and Verify

**Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: ALL PASS

**Step 2: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

**Step 3: Final commit if any fixes needed**

Only if tests or build revealed issues that needed fixing.
