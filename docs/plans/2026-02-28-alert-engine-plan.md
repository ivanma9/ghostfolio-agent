# Alert Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add proactive alerts that surface automatically on every chat message, with 24-hour per-alert cooldown.

**Architecture:** AlertEngine singleton with in-memory cooldown dict. Two-phase fetch (quotes+earnings for all holdings, then deep enrichment for flagged ones). Alerts injected into the user's message as context so the LLM naturally weaves them into its response.

**Tech Stack:** Python, asyncio, pytest, existing Finnhub/AlphaVantage/FMP clients, conviction score functions.

---

### Task 1: Alert Engine — Cooldown Logic

**Files:**
- Create: `src/ghostfolio_agent/alerts/__init__.py`
- Create: `src/ghostfolio_agent/alerts/engine.py`
- Test: `tests/unit/test_alert_engine.py`

**Step 1: Write the failing tests**

In `tests/unit/test_alert_engine.py`:

```python
import pytest
import time
from ghostfolio_agent.alerts.engine import AlertEngine, COOLDOWN_TTL


class TestCooldown:
    def test_new_alert_is_not_cooled_down(self):
        """Fresh engine has no fired alerts — everything passes cooldown."""
        engine = AlertEngine()
        assert engine._is_cooled_down("earnings:NVDA") is True

    def test_fired_alert_is_cooled_down(self):
        """Alert that just fired should be suppressed."""
        engine = AlertEngine()
        engine._record("earnings:NVDA")
        assert engine._is_cooled_down("earnings:NVDA") is False

    def test_different_alert_key_not_affected(self):
        """Firing one alert doesn't suppress a different one."""
        engine = AlertEngine()
        engine._record("earnings:NVDA")
        assert engine._is_cooled_down("big_mover:NVDA") is True
        assert engine._is_cooled_down("earnings:AAPL") is True

    def test_expired_alert_passes_cooldown(self):
        """Alert older than COOLDOWN_TTL should fire again."""
        engine = AlertEngine()
        engine._fired["earnings:NVDA"] = time.time() - COOLDOWN_TTL - 1
        assert engine._is_cooled_down("earnings:NVDA") is True

    def test_record_prunes_old_entries(self):
        """Recording a new alert prunes expired entries."""
        engine = AlertEngine()
        engine._fired["old:AAPL"] = time.time() - COOLDOWN_TTL - 100
        engine._fired["recent:MSFT"] = time.time()
        engine._record("new:NVDA")
        assert "old:AAPL" not in engine._fired
        assert "recent:MSFT" in engine._fired
        assert "new:NVDA" in engine._fired
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_alert_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ghostfolio_agent.alerts'`

**Step 3: Write minimal implementation**

Create `src/ghostfolio_agent/alerts/__init__.py`:

```python
```

Create `src/ghostfolio_agent/alerts/engine.py`:

```python
"""Alert Engine — proactive alerts on every chat message."""

import time
import structlog

logger = structlog.get_logger()

COOLDOWN_TTL = 86400  # 24 hours in seconds


class AlertEngine:
    def __init__(self):
        self._fired: dict[str, float] = {}  # alert_key -> timestamp

    def _is_cooled_down(self, key: str) -> bool:
        """Check if an alert key has passed its cooldown period."""
        fired_at = self._fired.get(key)
        if fired_at is None:
            return True
        return (time.time() - fired_at) > COOLDOWN_TTL

    def _record(self, key: str):
        """Record an alert as fired and prune expired entries."""
        self._fired[key] = time.time()
        cutoff = time.time() - COOLDOWN_TTL
        self._fired = {k: v for k, v in self._fired.items() if v > cutoff}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_alert_engine.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/alerts/__init__.py src/ghostfolio_agent/alerts/engine.py tests/unit/test_alert_engine.py
git commit -m "feat(alerts): add AlertEngine with cooldown logic"
```

---

### Task 2: Alert Condition Functions

**Files:**
- Modify: `src/ghostfolio_agent/alerts/engine.py`
- Test: `tests/unit/test_alert_engine.py`

**Step 1: Write the failing tests**

Append to `tests/unit/test_alert_engine.py`:

```python
from datetime import date, timedelta
from ghostfolio_agent.alerts.engine import (
    _check_earnings_proximity,
    _check_big_mover,
    _check_analyst_downgrade,
)


class TestCheckEarningsProximity:
    def test_earnings_in_2_days(self):
        today = date.today()
        earnings_date = (today + timedelta(days=2)).isoformat()
        earnings_data = [{"date": earnings_date}]
        result = _check_earnings_proximity("NVDA", earnings_data, today)
        assert result is not None
        assert "NVDA" in result
        assert "2 days" in result

    def test_earnings_in_3_days_triggers(self):
        today = date.today()
        earnings_date = (today + timedelta(days=3)).isoformat()
        earnings_data = [{"date": earnings_date}]
        result = _check_earnings_proximity("AAPL", earnings_data, today)
        assert result is not None

    def test_earnings_in_4_days_no_alert(self):
        today = date.today()
        earnings_date = (today + timedelta(days=4)).isoformat()
        earnings_data = [{"date": earnings_date}]
        result = _check_earnings_proximity("AAPL", earnings_data, today)
        assert result is None

    def test_no_earnings_data(self):
        result = _check_earnings_proximity("AAPL", [], date.today())
        assert result is None

    def test_none_earnings_data(self):
        result = _check_earnings_proximity("AAPL", None, date.today())
        assert result is None


class TestCheckBigMover:
    def test_down_5_percent(self):
        quote = {"dp": -5.0, "c": 187.42}
        result = _check_big_mover("TSLA", quote)
        assert result is not None
        assert "TSLA" in result
        assert "5.0%" in result

    def test_up_6_percent(self):
        quote = {"dp": 6.3, "c": 250.00}
        result = _check_big_mover("NVDA", quote)
        assert result is not None
        assert "NVDA" in result
        assert "6.3%" in result

    def test_4_percent_no_alert(self):
        quote = {"dp": 4.9, "c": 200.00}
        result = _check_big_mover("AAPL", quote)
        assert result is None

    def test_no_quote(self):
        result = _check_big_mover("AAPL", None)
        assert result is None

    def test_zero_change(self):
        quote = {"dp": 0.0, "c": 200.00}
        result = _check_big_mover("AAPL", quote)
        assert result is None


class TestCheckAnalystDowngrade:
    def test_sell_consensus(self):
        """Mostly sell/strongSell analysts triggers alert."""
        analyst = [{"strongBuy": 1, "buy": 1, "hold": 2, "sell": 4, "strongSell": 3}]
        result = _check_analyst_downgrade("MSFT", analyst)
        assert result is not None
        assert "MSFT" in result

    def test_buy_consensus_no_alert(self):
        analyst = [{"strongBuy": 10, "buy": 15, "hold": 5, "sell": 1, "strongSell": 0}]
        result = _check_analyst_downgrade("AAPL", analyst)
        assert result is None

    def test_no_analyst_data(self):
        result = _check_analyst_downgrade("AAPL", None)
        assert result is None

    def test_empty_analyst_data(self):
        result = _check_analyst_downgrade("AAPL", [])
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_alert_engine.py::TestCheckEarningsProximity -v`
Expected: FAIL with `ImportError: cannot import name '_check_earnings_proximity'`

**Step 3: Write the implementation**

Add to `src/ghostfolio_agent/alerts/engine.py`:

```python
from datetime import date


def _check_earnings_proximity(symbol: str, earnings_data: list[dict] | None, today: date) -> str | None:
    """Return alert string if earnings within 3 days."""
    if not earnings_data:
        return None
    for entry in earnings_data:
        date_str = entry.get("date", "")
        try:
            earnings_date = date.fromisoformat(date_str)
            days_until = (earnings_date - today).days
            if 0 <= days_until <= 3:
                return f"{symbol} earnings in {days_until} days ({date_str}) — consider position sizing"
        except (ValueError, TypeError):
            continue
    return None


def _check_big_mover(symbol: str, quote_data: dict | None) -> str | None:
    """Return alert string if |daily change| >= 5%."""
    if not quote_data:
        return None
    dp = quote_data.get("dp", 0) or 0
    price = quote_data.get("c", 0) or 0
    if abs(dp) >= 5.0:
        direction = "up" if dp > 0 else "down"
        return f"{symbol} {direction} {abs(dp):.1f}% today (${price:,.2f}) — significant daily move"
    return None


def _check_analyst_downgrade(symbol: str, analyst_data: list[dict] | None) -> str | None:
    """Return alert string if analyst consensus is Sell or worse."""
    if not analyst_data:
        return None
    entry = analyst_data[0]
    strong_buy = entry.get("strongBuy", 0)
    buy = entry.get("buy", 0)
    hold = entry.get("hold", 0)
    sell = entry.get("sell", 0)
    strong_sell = entry.get("strongSell", 0)
    total = strong_buy + buy + hold + sell + strong_sell
    if total == 0:
        return None
    bearish = sell + strong_sell
    bullish = strong_buy + buy
    if bearish / total >= 0.5:
        return f"{symbol} analyst consensus shifted to Sell ({bullish} of {total} analysts bullish) — monitor closely"
    return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_alert_engine.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/alerts/engine.py tests/unit/test_alert_engine.py
git commit -m "feat(alerts): add earnings, big mover, and analyst downgrade checks"
```

---

### Task 3: Low Conviction Alert Check

**Files:**
- Modify: `src/ghostfolio_agent/alerts/engine.py`
- Test: `tests/unit/test_alert_engine.py`

This is separate because it depends on the conviction score functions and needs Phase 2 data.

**Step 1: Write the failing tests**

Append to `tests/unit/test_alert_engine.py`:

```python
from ghostfolio_agent.alerts.engine import _check_low_conviction


class TestCheckLowConviction:
    def test_low_conviction_triggers(self):
        """Conviction < 40 should trigger alert."""
        analyst = [{"strongBuy": 1, "buy": 1, "hold": 3, "sell": 5, "strongSell": 5}]
        pt = [{"targetConsensus": 90.0}]
        news = [
            {"overall_sentiment_label": "Bearish"},
            {"overall_sentiment_label": "Bearish"},
        ]
        earnings = []
        result = _check_low_conviction("TSLA", analyst, pt, news, earnings, 100.0)
        assert result is not None
        assert "TSLA" in result
        assert "/100" in result

    def test_high_conviction_no_alert(self):
        """Conviction >= 40 should not trigger alert."""
        analyst = [{"strongBuy": 10, "buy": 15, "hold": 5, "sell": 0, "strongSell": 0}]
        pt = [{"targetConsensus": 250.0}]
        news = [
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Bullish"},
        ]
        earnings = []
        result = _check_low_conviction("AAPL", analyst, pt, news, earnings, 200.0)
        assert result is None

    def test_no_data_no_alert(self):
        """No enrichment data should not trigger alert."""
        result = _check_low_conviction("AAPL", None, None, None, None, 0)
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_alert_engine.py::TestCheckLowConviction -v`
Expected: FAIL with `ImportError: cannot import name '_check_low_conviction'`

**Step 3: Write the implementation**

Add to `src/ghostfolio_agent/alerts/engine.py`:

```python
from ghostfolio_agent.tools.conviction_score import (
    compute_analyst_score,
    compute_price_target_score,
    compute_sentiment_score,
    compute_earnings_score,
    compute_composite,
    ANALYST_WEIGHT,
    PRICE_TARGET_WEIGHT,
    SENTIMENT_WEIGHT,
    EARNINGS_WEIGHT,
)


def _check_low_conviction(
    symbol: str,
    analyst_data: list[dict] | None,
    pt_data: list[dict] | None,
    news_data: list[dict] | None,
    earnings_data: list[dict] | None,
    market_price: float,
) -> str | None:
    """Return alert string if conviction score < 40."""
    components = []

    a_score, a_expl = compute_analyst_score(analyst_data)
    if a_score is not None:
        components.append(("analyst", a_score, a_expl, ANALYST_WEIGHT))

    pt_score, pt_expl = compute_price_target_score(pt_data, market_price)
    if pt_score is not None:
        components.append(("price_target", pt_score, pt_expl, PRICE_TARGET_WEIGHT))

    s_score, s_expl = compute_sentiment_score(news_data)
    if s_score is not None:
        components.append(("sentiment", s_score, s_expl, SENTIMENT_WEIGHT))

    e_score, e_expl = compute_earnings_score(earnings_data)
    components.append(("earnings", e_score, e_expl, EARNINGS_WEIGHT))

    composite, label, _ = compute_composite(components)
    if composite is not None and composite < 40:
        return f"{symbol} conviction score dropped to {composite}/100 ({label}) — review position"
    return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_alert_engine.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/alerts/engine.py tests/unit/test_alert_engine.py
git commit -m "feat(alerts): add low conviction check using existing scoring functions"
```

---

### Task 4: check_alerts Method — Full Scan

**Files:**
- Modify: `src/ghostfolio_agent/alerts/engine.py`
- Test: `tests/unit/test_alert_engine.py`

**Step 1: Write the failing tests**

Append to `tests/unit/test_alert_engine.py`:

```python
from unittest.mock import MagicMock, AsyncMock
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient


HOLDINGS_RESPONSE = {
    "holdings": {
        "AAPL": {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "quantity": 10,
            "valueInBaseCurrency": 2000.0,
        },
        "TSLA": {
            "symbol": "TSLA",
            "name": "Tesla Inc.",
            "quantity": 5,
            "valueInBaseCurrency": 1000.0,
        },
    }
}


@pytest.fixture
def mock_ghostfolio():
    client = MagicMock(spec=GhostfolioClient)
    client.get_portfolio_holdings = AsyncMock(return_value=HOLDINGS_RESPONSE)
    return client


@pytest.fixture
def mock_finnhub():
    client = MagicMock(spec=FinnhubClient)
    today = date.today()
    earnings_date = (today + timedelta(days=2)).isoformat()

    async def mock_quote(symbol):
        return {
            "AAPL": {"c": 200.0, "dp": -6.0, "d": -12.0},  # big mover
            "TSLA": {"c": 180.0, "dp": 1.0, "d": 1.8},
        }.get(symbol, {"c": 0, "dp": 0, "d": 0})

    async def mock_earnings(symbol):
        return {
            "TSLA": [{"date": earnings_date}],  # earnings soon
        }.get(symbol, [])

    async def mock_analyst(symbol):
        return {
            "AAPL": [{"strongBuy": 1, "buy": 1, "hold": 2, "sell": 4, "strongSell": 3}],
        }.get(symbol, [])

    client.get_quote = MagicMock(side_effect=mock_quote)
    client.get_earnings_calendar = MagicMock(side_effect=mock_earnings)
    client.get_analyst_recommendations = MagicMock(side_effect=mock_analyst)
    return client


class TestCheckAlerts:
    @pytest.mark.asyncio
    async def test_finds_big_mover_and_earnings(self, mock_ghostfolio, mock_finnhub):
        """Should detect AAPL big mover and TSLA earnings."""
        engine = AlertEngine()
        alerts = await engine.check_alerts(mock_ghostfolio, finnhub=mock_finnhub)
        alert_text = "\n".join(alerts)
        assert "AAPL" in alert_text  # big mover
        assert "TSLA" in alert_text  # earnings proximity

    @pytest.mark.asyncio
    async def test_cooldown_suppresses_repeat(self, mock_ghostfolio, mock_finnhub):
        """Same alerts should not fire twice within cooldown."""
        engine = AlertEngine()
        alerts1 = await engine.check_alerts(mock_ghostfolio, finnhub=mock_finnhub)
        assert len(alerts1) > 0
        alerts2 = await engine.check_alerts(mock_ghostfolio, finnhub=mock_finnhub)
        assert len(alerts2) == 0

    @pytest.mark.asyncio
    async def test_no_clients_returns_empty(self, mock_ghostfolio):
        """No external clients means no alerts."""
        engine = AlertEngine()
        alerts = await engine.check_alerts(mock_ghostfolio)
        assert alerts == []

    @pytest.mark.asyncio
    async def test_empty_portfolio_returns_empty(self, mock_finnhub):
        """Empty portfolio returns no alerts."""
        client = MagicMock(spec=GhostfolioClient)
        client.get_portfolio_holdings = AsyncMock(return_value={"holdings": {}})
        engine = AlertEngine()
        alerts = await engine.check_alerts(client, finnhub=mock_finnhub)
        assert alerts == []

    @pytest.mark.asyncio
    async def test_holdings_fetch_failure_returns_empty(self, mock_finnhub):
        """If holdings fetch fails, return empty alerts gracefully."""
        client = MagicMock(spec=GhostfolioClient)
        client.get_portfolio_holdings = AsyncMock(side_effect=Exception("API error"))
        engine = AlertEngine()
        alerts = await engine.check_alerts(client, finnhub=mock_finnhub)
        assert alerts == []
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_alert_engine.py::TestCheckAlerts -v`
Expected: FAIL — `check_alerts` method doesn't exist yet or has wrong signature

**Step 3: Write the implementation**

Add the full `check_alerts` method to the `AlertEngine` class in `engine.py`:

```python
import asyncio
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient


async def _safe_fetch(coro, label: str):
    """Run a coroutine and return None on any exception."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("alert_fetch_failed", label=label, error=str(exc))
        return None


# Inside the AlertEngine class:

    async def check_alerts(
        self,
        client: GhostfolioClient,
        finnhub: FinnhubClient | None = None,
        alpha_vantage: AlphaVantageClient | None = None,
        fmp: FMPClient | None = None,
    ) -> list[str]:
        """Run alert scan against all holdings. Returns list of alert strings."""
        if not finnhub and not alpha_vantage and not fmp:
            return []

        try:
            data = await client.get_portfolio_holdings()
        except Exception as e:
            logger.warning("alert_holdings_failed", error=str(e))
            return []

        raw_holdings = data.get("holdings", {})
        if isinstance(raw_holdings, dict):
            holdings = list(raw_holdings.values())
        else:
            holdings = list(raw_holdings)

        if not holdings:
            return []

        symbols = [h.get("symbol", "") for h in holdings if h.get("symbol")]
        today = date.today()

        # Phase 1: quotes + earnings for all holdings (Finnhub only)
        quote_tasks = []
        earnings_tasks = []
        for sym in symbols:
            if finnhub:
                quote_tasks.append(_safe_fetch(finnhub.get_quote(sym), f"quote_{sym}"))
                earnings_tasks.append(_safe_fetch(finnhub.get_earnings_calendar(sym), f"earnings_{sym}"))
            else:
                async def _none():
                    return None
                quote_tasks.append(_none())
                earnings_tasks.append(_none())

        all_results = await asyncio.gather(*(quote_tasks + earnings_tasks))
        quotes = dict(zip(symbols, all_results[:len(symbols)]))
        earnings = dict(zip(symbols, all_results[len(symbols):]))

        # Evaluate Phase 1 alerts and identify flagged symbols for Phase 2
        alerts: list[str] = []
        flagged_symbols: set[str] = set()

        for sym in symbols:
            # Earnings proximity
            key = f"earnings:{sym}"
            result = _check_earnings_proximity(sym, earnings.get(sym), today)
            if result and self._is_cooled_down(key):
                alerts.append(result)
                self._record(key)
                flagged_symbols.add(sym)

            # Big mover
            key = f"big_mover:{sym}"
            result = _check_big_mover(sym, quotes.get(sym))
            if result and self._is_cooled_down(key):
                alerts.append(result)
                self._record(key)
                flagged_symbols.add(sym)

        # Phase 2: deep enrichment for flagged symbols only
        if flagged_symbols and (finnhub or alpha_vantage or fmp):
            enrich_tasks = {}
            for sym in flagged_symbols:
                sym_tasks = {}
                if finnhub:
                    sym_tasks["analyst"] = _safe_fetch(finnhub.get_analyst_recommendations(sym), f"analyst_{sym}")
                if alpha_vantage:
                    sym_tasks["news"] = _safe_fetch(alpha_vantage.get_news_sentiment(sym), f"news_{sym}")
                if fmp:
                    sym_tasks["pt"] = _safe_fetch(fmp.get_price_target_consensus(sym), f"pt_{sym}")
                enrich_tasks[sym] = sym_tasks

            flat_keys = []
            flat_coros = []
            for sym, tasks in enrich_tasks.items():
                for task_key, coro in tasks.items():
                    flat_keys.append((sym, task_key))
                    flat_coros.append(coro)

            flat_results = await asyncio.gather(*flat_coros) if flat_coros else []
            enriched = {sym: {} for sym in flagged_symbols}
            for (sym, task_key), result in zip(flat_keys, flat_results):
                enriched[sym][task_key] = result

            for sym in flagged_symbols:
                sym_data = enriched[sym]
                market_price = (quotes.get(sym) or {}).get("c", 0)

                # Analyst downgrade
                key = f"analyst_downgrade:{sym}"
                result = _check_analyst_downgrade(sym, sym_data.get("analyst"))
                if result and self._is_cooled_down(key):
                    alerts.append(result)
                    self._record(key)

                # Low conviction
                key = f"low_conviction:{sym}"
                result = _check_low_conviction(
                    sym,
                    sym_data.get("analyst"),
                    sym_data.get("pt"),
                    sym_data.get("news"),
                    earnings.get(sym),
                    market_price,
                )
                if result and self._is_cooled_down(key):
                    alerts.append(result)
                    self._record(key)

        return alerts
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_alert_engine.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/alerts/engine.py tests/unit/test_alert_engine.py
git commit -m "feat(alerts): add check_alerts method with two-phase fetch and cooldown"
```

---

### Task 5: Integrate Alert Engine into Chat Flow

**Files:**
- Modify: `src/ghostfolio_agent/api/chat.py`
- Modify: `src/ghostfolio_agent/main.py`

**Step 1: Modify `chat.py` to run alert check**

In `src/ghostfolio_agent/api/chat.py`, add the alert engine import and singleton, then inject alerts before agent invocation.

Add near top imports:

```python
from ghostfolio_agent.alerts.engine import AlertEngine
```

Add module-level singleton:

```python
_alert_engine: AlertEngine | None = None


def _get_alert_engine() -> AlertEngine:
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine()
    return _alert_engine
```

In the `chat()` function, after `content = request.message` and the paper trading block (around line 186), before `config = {"configurable"...}`, add:

```python
        # Run alert check
        alert_engine = _get_alert_engine()
        settings = get_settings()
        finnhub = FinnhubClient(api_key=settings.finnhub_api_key) if settings.finnhub_api_key else None
        alpha_vantage_client = AlphaVantageClient(api_key=settings.alpha_vantage_api_key) if settings.alpha_vantage_api_key else None
        fmp_client = FMPClient(api_key=settings.fmp_api_key) if settings.fmp_api_key else None

        try:
            alerts = await alert_engine.check_alerts(
                _get_client(), finnhub=finnhub, alpha_vantage=alpha_vantage_client, fmp=fmp_client
            )
        except Exception as e:
            logger.warning("alert_check_failed", error=str(e))
            alerts = []

        if alerts:
            alert_block = "ALERTS:\n" + "\n".join(f"- {a}" for a in alerts)
            content = f"{alert_block}\n\nUser message: {content}"
```

**Step 2: No changes needed to `main.py`**

The AlertEngine singleton is lazy-initialized in `chat.py` via `_get_alert_engine()`, matching the existing pattern used by `_get_client()` and `_get_checkpointer()`. No lifespan changes needed.

**Step 3: Run full test suite to verify nothing broke**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/ghostfolio_agent/api/chat.py
git commit -m "feat(alerts): integrate alert engine into chat flow"
```

---

### Task 6: Verify Full Test Suite

**Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests PASS

**Step 2: Commit docs update**

Update the design doc status from Draft to Implemented:

In `docs/plans/2026-02-28-alert-engine-design.md`, change:
```
**Status:** Draft
```
to:
```
**Status:** Implemented
```

```bash
git add docs/plans/2026-02-28-alert-engine-design.md
git commit -m "docs: mark alert engine design as implemented"
```
