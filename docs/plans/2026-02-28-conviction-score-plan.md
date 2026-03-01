# Conviction Score Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `conviction_score` tool that computes a 0–100 composite score from analyst consensus, price target upside, news sentiment, and earnings proximity — with full sub-score transparency.

**Architecture:** Pure scoring functions in `conviction_score.py` that take raw API data and return `(score, explanation)` tuples. A factory creates the LangChain tool. The same scoring functions are imported by `holding_detail.py` to embed the composite score in its Smart Summary section.

**Tech Stack:** Python, LangChain tools, Finnhub/Alpha Vantage/FMP clients, pytest

---

### Task 1: Scoring Functions — Analyst Consensus

**Files:**
- Create: `src/ghostfolio_agent/tools/conviction_score.py`
- Create: `tests/unit/test_conviction_score.py`

**Step 1: Write the failing tests**

In `tests/unit/test_conviction_score.py`:

```python
import pytest
from ghostfolio_agent.tools.conviction_score import compute_analyst_score


class TestAnalystScore:
    def test_all_strong_buy(self):
        """All strong buy → 100."""
        data = [{"strongBuy": 10, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}]
        score, explanation = compute_analyst_score(data)
        assert score == 100
        assert "10 of 10" in explanation

    def test_all_strong_sell(self):
        """All strong sell → 0."""
        data = [{"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 10}]
        score, explanation = compute_analyst_score(data)
        assert score == 0

    def test_mixed(self):
        """12 strongBuy + 18 buy + 6 hold + 1 sell → high score."""
        data = [{"strongBuy": 12, "buy": 18, "hold": 6, "sell": 1, "strongSell": 0}]
        score, explanation = compute_analyst_score(data)
        assert 70 <= score <= 90
        assert "30 of 37" in explanation

    def test_all_hold(self):
        """All hold → 50."""
        data = [{"strongBuy": 0, "buy": 0, "hold": 10, "sell": 0, "strongSell": 0}]
        score, explanation = compute_analyst_score(data)
        assert score == 50

    def test_none_data(self):
        """None input → None."""
        score, explanation = compute_analyst_score(None)
        assert score is None
        assert explanation == "No analyst data"

    def test_empty_list(self):
        """Empty list → None."""
        score, explanation = compute_analyst_score([])
        assert score is None
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestAnalystScore -v`
Expected: FAIL — ImportError (module doesn't exist yet)

**Step 3: Write minimal implementation**

In `src/ghostfolio_agent/tools/conviction_score.py`:

```python
"""Conviction Score — composite 0-100 score from multiple market signals."""


def compute_analyst_score(
    analyst_data: list[dict] | None,
) -> tuple[int | None, str]:
    """Score analyst consensus 0-100.

    Weighted formula: (strongBuy*2 + buy*1 + hold*0 - sell*1 - strongSell*2)
    mapped from [-2, +2] range to [0, 100].
    """
    if not analyst_data:
        return None, "No analyst data"

    entry = analyst_data[0]
    strong_buy = entry.get("strongBuy", 0)
    buy = entry.get("buy", 0)
    hold = entry.get("hold", 0)
    sell = entry.get("sell", 0)
    strong_sell = entry.get("strongSell", 0)
    total = strong_buy + buy + hold + sell + strong_sell

    if total == 0:
        return None, "No analyst data"

    # Weighted score: range is [-2*total, +2*total], map to [0, 100]
    raw = strong_buy * 2 + buy * 1 + hold * 0 - sell * 1 - strong_sell * 2
    score = round((raw + 2 * total) / (4 * total) * 100)
    score = max(0, min(100, score))

    bullish = strong_buy + buy
    explanation = f"{bullish} of {total} analysts bullish"
    return score, explanation
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestAnalystScore -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score
git add src/ghostfolio_agent/tools/conviction_score.py tests/unit/test_conviction_score.py
git commit -m "feat: add analyst consensus scoring function for conviction score"
```

---

### Task 2: Scoring Functions — Price Target Upside

**Files:**
- Modify: `src/ghostfolio_agent/tools/conviction_score.py`
- Modify: `tests/unit/test_conviction_score.py`

**Step 1: Write the failing tests**

Append to `tests/unit/test_conviction_score.py`:

```python
from ghostfolio_agent.tools.conviction_score import compute_price_target_score


class TestPriceTargetScore:
    def test_large_upside(self):
        """+30% upside or more → 100."""
        data = [{"targetConsensus": 260.0}]
        score, explanation = compute_price_target_score(data, 200.0)
        assert score == 100
        assert "+30.0%" in explanation

    def test_large_downside(self):
        """-30% or worse → 0."""
        data = [{"targetConsensus": 140.0}]
        score, explanation = compute_price_target_score(data, 200.0)
        assert score == 0

    def test_no_change(self):
        """Target equals market → 50."""
        data = [{"targetConsensus": 200.0}]
        score, explanation = compute_price_target_score(data, 200.0)
        assert score == 50

    def test_moderate_upside(self):
        """+15% upside → 75."""
        data = [{"targetConsensus": 230.0}]
        score, explanation = compute_price_target_score(data, 200.0)
        assert score == 75
        assert "+15.0%" in explanation

    def test_none_data(self):
        """None input → None."""
        score, explanation = compute_price_target_score(None, 200.0)
        assert score is None

    def test_zero_market_price(self):
        """Zero market price → None (avoid division by zero)."""
        data = [{"targetConsensus": 200.0}]
        score, explanation = compute_price_target_score(data, 0.0)
        assert score is None
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestPriceTargetScore -v`
Expected: FAIL — ImportError

**Step 3: Write minimal implementation**

Append to `conviction_score.py`:

```python
def compute_price_target_score(
    consensus_data: list[dict] | None,
    market_price: float,
) -> tuple[int | None, str]:
    """Score price target upside 0-100.

    Linear mapping: +30% upside = 100, 0% = 50, -30% downside = 0.
    Clamped to [0, 100].
    """
    if not consensus_data or not market_price:
        return None, "No price target data"

    target = consensus_data[0].get("targetConsensus", 0)
    if not target:
        return None, "No price target data"

    upside_pct = (target - market_price) / market_price * 100
    # Linear: -30% → 0, 0% → 50, +30% → 100
    score = round(50 + (upside_pct / 30) * 50)
    score = max(0, min(100, score))

    sign = "+" if upside_pct >= 0 else ""
    explanation = f"{sign}{upside_pct:.1f}% implied upside (${target:,.2f} target)"
    return score, explanation
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestPriceTargetScore -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score
git add src/ghostfolio_agent/tools/conviction_score.py tests/unit/test_conviction_score.py
git commit -m "feat: add price target upside scoring function"
```

---

### Task 3: Scoring Functions — News Sentiment & Earnings Proximity

**Files:**
- Modify: `src/ghostfolio_agent/tools/conviction_score.py`
- Modify: `tests/unit/test_conviction_score.py`

**Step 1: Write the failing tests**

Append to `tests/unit/test_conviction_score.py`:

```python
from datetime import date, timedelta
from ghostfolio_agent.tools.conviction_score import (
    compute_sentiment_score,
    compute_earnings_score,
)


class TestSentimentScore:
    def test_all_bullish(self):
        """All bullish articles → 100."""
        news = [
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Somewhat-Bullish"},
        ]
        score, explanation = compute_sentiment_score(news)
        assert score == 100
        assert "2 of 2" in explanation

    def test_all_bearish(self):
        """All bearish articles → 0."""
        news = [
            {"overall_sentiment_label": "Bearish"},
            {"overall_sentiment_label": "Somewhat-Bearish"},
        ]
        score, explanation = compute_sentiment_score(news)
        assert score == 0

    def test_mixed(self):
        """3 bullish, 1 neutral, 1 bearish → 60."""
        news = [
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Somewhat-Bullish"},
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Neutral"},
            {"overall_sentiment_label": "Bearish"},
        ]
        score, explanation = compute_sentiment_score(news)
        assert score == 60
        assert "3 of 5" in explanation

    def test_all_neutral(self):
        """All neutral → 50."""
        news = [{"overall_sentiment_label": "Neutral"}] * 4
        score, explanation = compute_sentiment_score(news)
        assert score == 50

    def test_none_data(self):
        """None → None."""
        score, explanation = compute_sentiment_score(None)
        assert score is None

    def test_empty_list(self):
        """Empty → None."""
        score, explanation = compute_sentiment_score([])
        assert score is None


class TestEarningsScore:
    def test_no_upcoming(self):
        """No earnings data → 75 (stable)."""
        score, explanation = compute_earnings_score(None)
        assert score == 75
        assert "No upcoming" in explanation

    def test_earnings_within_14_days(self):
        """Earnings in 8 days → 50 (uncertainty)."""
        earn_date = (date.today() + timedelta(days=8)).isoformat()
        data = [{"date": earn_date}]
        score, explanation = compute_earnings_score(data)
        assert score == 50
        assert "8 days" in explanation

    def test_earnings_far_away(self):
        """Earnings 45 days away → 75 (stable, same as no upcoming)."""
        earn_date = (date.today() + timedelta(days=45)).isoformat()
        data = [{"date": earn_date}]
        score, explanation = compute_earnings_score(data)
        assert score == 75

    def test_earnings_today(self):
        """Earnings today → 50."""
        earn_date = date.today().isoformat()
        data = [{"date": earn_date}]
        score, explanation = compute_earnings_score(data)
        assert score == 50
        assert "0 days" in explanation

    def test_empty_list(self):
        """Empty list → 75 (stable)."""
        score, explanation = compute_earnings_score([])
        assert score == 75
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestSentimentScore tests/unit/test_conviction_score.py::TestEarningsScore -v`
Expected: FAIL — ImportError

**Step 3: Write minimal implementation**

Append to `conviction_score.py`:

```python
from datetime import date


def compute_sentiment_score(
    news_data: list[dict] | None,
) -> tuple[int | None, str]:
    """Score news sentiment 0-100.

    Maps bullish/bearish article ratio linearly.
    Bullish + Somewhat-Bullish count as bullish.
    Bearish + Somewhat-Bearish count as bearish.
    Neutral counts as 0.5 (maps to 50).
    """
    if not news_data:
        return None, "No news data"

    bullish_labels = {"Bullish", "Somewhat_Bullish", "Somewhat-Bullish"}
    bearish_labels = {"Bearish", "Somewhat_Bearish", "Somewhat-Bearish"}

    total = len(news_data)
    bullish = sum(1 for a in news_data if a.get("overall_sentiment_label") in bullish_labels)
    bearish = sum(1 for a in news_data if a.get("overall_sentiment_label") in bearish_labels)
    neutral = total - bullish - bearish

    # Score: bullish=1, neutral=0.5, bearish=0 per article
    raw = (bullish * 1.0 + neutral * 0.5 + bearish * 0.0) / total
    score = round(raw * 100)
    score = max(0, min(100, score))

    explanation = f"{bullish} of {total} articles positive"
    return score, explanation


def compute_earnings_score(
    earnings_data: list[dict] | None,
) -> tuple[int, str]:
    """Score earnings proximity 0-100.

    No upcoming earnings = 75 (stable).
    Reporting within 14 days = 50 (uncertainty).
    Reporting > 14 days away = 75 (stable).
    Always returns a score (never None) since absence of data is informative.
    """
    if not earnings_data:
        return 75, "No upcoming earnings (stable)"

    today = date.today()
    for entry in earnings_data:
        date_str = entry.get("date", "")
        try:
            earnings_date = date.fromisoformat(date_str)
            days_until = (earnings_date - today).days
            if 0 <= days_until <= 14:
                return 50, f"Reporting in {days_until} days ({date_str})"
        except (ValueError, TypeError):
            continue

    return 75, "No upcoming earnings (stable)"
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestSentimentScore tests/unit/test_conviction_score.py::TestEarningsScore -v`
Expected: PASS (all 11 tests)

**Step 5: Commit**

```bash
cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score
git add src/ghostfolio_agent/tools/conviction_score.py tests/unit/test_conviction_score.py
git commit -m "feat: add sentiment and earnings proximity scoring functions"
```

---

### Task 4: Composite Score & Label

**Files:**
- Modify: `src/ghostfolio_agent/tools/conviction_score.py`
- Modify: `tests/unit/test_conviction_score.py`

**Step 1: Write the failing tests**

Append to `tests/unit/test_conviction_score.py`:

```python
from ghostfolio_agent.tools.conviction_score import compute_composite, score_to_label

WEIGHTS = {"analyst": 40, "price_target": 30, "sentiment": 20, "earnings": 10}


class TestComposite:
    def test_all_components(self):
        """All 4 components present — weighted average."""
        components = [
            ("analyst", 80, "18 of 24 bullish", 40),
            ("price_target", 70, "+12% upside", 30),
            ("sentiment", 60, "3 of 5 positive", 20),
            ("earnings", 50, "Reporting in 8 days", 10),
        ]
        score, label, details = compute_composite(components)
        # (80*40 + 70*30 + 60*20 + 50*10) / 100 = (3200+2100+1200+500)/100 = 70
        assert score == 70
        assert label == "Buy"
        assert len(details) == 4

    def test_missing_one_component(self):
        """3 components — weights redistribute."""
        components = [
            ("analyst", 80, "18 of 24 bullish", 40),
            ("price_target", 70, "+12% upside", 30),
            ("earnings", 50, "Reporting in 8 days", 10),
        ]
        score, label, details = compute_composite(components)
        # Total weight = 80, redistributed: analyst=40/80*100=50, pt=30/80*100=37.5, earn=10/80*100=12.5
        # (80*50 + 70*37.5 + 50*12.5) / 100 = (4000+2625+625)/100 = 72.5 → 72 or 73
        assert 72 <= score <= 73
        assert label == "Buy"

    def test_single_component(self):
        """Only one component — uses its score directly."""
        components = [
            ("analyst", 85, "20 of 24 bullish", 40),
        ]
        score, label, details = compute_composite(components)
        assert score == 85
        assert label == "Strong Buy"

    def test_empty_components(self):
        """No components → None."""
        score, label, details = compute_composite([])
        assert score is None
        assert label == "Insufficient Data"


class TestScoreToLabel:
    def test_strong_sell(self):
        assert score_to_label(10) == "Strong Sell"
        assert score_to_label(0) == "Strong Sell"
        assert score_to_label(20) == "Strong Sell"

    def test_sell(self):
        assert score_to_label(21) == "Sell"
        assert score_to_label(40) == "Sell"

    def test_neutral(self):
        assert score_to_label(41) == "Neutral"
        assert score_to_label(60) == "Neutral"

    def test_buy(self):
        assert score_to_label(61) == "Buy"
        assert score_to_label(80) == "Buy"

    def test_strong_buy(self):
        assert score_to_label(81) == "Strong Buy"
        assert score_to_label(100) == "Strong Buy"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestComposite tests/unit/test_conviction_score.py::TestScoreToLabel -v`
Expected: FAIL — ImportError

**Step 3: Write minimal implementation**

Append to `conviction_score.py`:

```python
def score_to_label(score: int) -> str:
    """Map 0-100 score to conviction label."""
    if score <= 20:
        return "Strong Sell"
    elif score <= 40:
        return "Sell"
    elif score <= 60:
        return "Neutral"
    elif score <= 80:
        return "Buy"
    else:
        return "Strong Buy"


def compute_composite(
    components: list[tuple[str, int, str, int]],
) -> tuple[int | None, str, list[dict]]:
    """Compute weighted composite from (name, score, explanation, weight) tuples.

    Redistributes weights proportionally if some components are missing.
    Returns (composite_score, label, detail_list).
    """
    if not components:
        return None, "Insufficient Data", []

    total_weight = sum(w for _, _, _, w in components)
    if total_weight == 0:
        return None, "Insufficient Data", []

    weighted_sum = sum(score * weight for _, score, _, weight in components)
    composite = round(weighted_sum / total_weight)
    composite = max(0, min(100, composite))
    label = score_to_label(composite)

    details = []
    for name, score, explanation, weight in components:
        redistributed_pct = round(weight / total_weight * 100)
        details.append({
            "name": name,
            "score": score,
            "explanation": explanation,
            "weight": redistributed_pct,
        })

    return composite, label, details
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestComposite tests/unit/test_conviction_score.py::TestScoreToLabel -v`
Expected: PASS (all 9 tests)

**Step 5: Commit**

```bash
cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score
git add src/ghostfolio_agent/tools/conviction_score.py tests/unit/test_conviction_score.py
git commit -m "feat: add composite score and label mapping"
```

---

### Task 5: Conviction Score Tool (LangChain)

**Files:**
- Modify: `src/ghostfolio_agent/tools/conviction_score.py`
- Modify: `tests/unit/test_conviction_score.py`

**Step 1: Write the failing tests**

Append to `tests/unit/test_conviction_score.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from ghostfolio_agent.tools.conviction_score import create_conviction_score_tool


ANALYST_MOCK = [
    {"period": "2026-03-01", "strongBuy": 12, "buy": 18, "hold": 6, "sell": 1, "strongSell": 0}
]

NEWS_MOCK = [
    {"title": "Apple beats earnings", "overall_sentiment_label": "Bullish", "source": "Reuters"},
    {"title": "Tech rally continues", "overall_sentiment_label": "Somewhat-Bullish", "source": "CNBC"},
    {"title": "Market concerns", "overall_sentiment_label": "Bearish", "source": "WSJ"},
]

PT_CONSENSUS_MOCK = [
    {"symbol": "AAPL", "targetConsensus": 220.50}
]

QUOTE_MOCK = {"c": 195.50, "h": 198.0, "l": 193.0, "o": 194.0, "pc": 193.50}


class TestConvictionScoreTool:
    @pytest.mark.asyncio
    async def test_full_score_output(self):
        """All clients configured — returns score with all 4 components."""
        finnhub = MagicMock()
        finnhub.get_analyst_recommendations = AsyncMock(return_value=ANALYST_MOCK)
        finnhub.get_earnings_calendar = AsyncMock(return_value=[])
        finnhub.get_quote = AsyncMock(return_value=QUOTE_MOCK)

        alpha_vantage = MagicMock()
        alpha_vantage.get_news_sentiment = AsyncMock(return_value=NEWS_MOCK)

        fmp = MagicMock()
        fmp.get_price_target_consensus = AsyncMock(return_value=PT_CONSENSUS_MOCK)

        tool = create_conviction_score_tool(
            finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Conviction Score" in result
        assert "/100" in result
        assert "Analyst Consensus" in result
        assert "Price Target Upside" in result
        assert "News Sentiment" in result
        assert "Earnings Proximity" in result

    @pytest.mark.asyncio
    async def test_missing_alpha_vantage(self):
        """No Alpha Vantage — 3 components, sentiment shows N/A."""
        finnhub = MagicMock()
        finnhub.get_analyst_recommendations = AsyncMock(return_value=ANALYST_MOCK)
        finnhub.get_earnings_calendar = AsyncMock(return_value=[])
        finnhub.get_quote = AsyncMock(return_value=QUOTE_MOCK)

        fmp = MagicMock()
        fmp.get_price_target_consensus = AsyncMock(return_value=PT_CONSENSUS_MOCK)

        tool = create_conviction_score_tool(finnhub=finnhub, fmp=fmp)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Conviction Score" in result
        assert "/100" in result
        assert "N/A" in result

    @pytest.mark.asyncio
    async def test_no_clients(self):
        """No clients configured — error message."""
        tool = create_conviction_score_tool()
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "not available" in result.lower() or "no data sources" in result.lower()

    @pytest.mark.asyncio
    async def test_api_errors_graceful(self):
        """All APIs error — graceful degradation."""
        finnhub = MagicMock()
        finnhub.get_analyst_recommendations = AsyncMock(side_effect=RuntimeError("down"))
        finnhub.get_earnings_calendar = AsyncMock(side_effect=RuntimeError("down"))
        finnhub.get_quote = AsyncMock(side_effect=RuntimeError("down"))

        alpha_vantage = MagicMock()
        alpha_vantage.get_news_sentiment = AsyncMock(side_effect=RuntimeError("down"))

        fmp = MagicMock()
        fmp.get_price_target_consensus = AsyncMock(side_effect=RuntimeError("down"))

        tool = create_conviction_score_tool(
            finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        # Should not crash, should indicate insufficient data
        assert "down" not in result.lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestConvictionScoreTool -v`
Expected: FAIL — ImportError

**Step 3: Write minimal implementation**

Add imports at top of `conviction_score.py`:

```python
import asyncio
import structlog
from langchain_core.tools import tool
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient

logger = structlog.get_logger()
```

Add `_safe_fetch` and the factory function:

```python
async def _safe_fetch(coro, label: str):
    """Run a coroutine and return None on any exception."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("conviction_fetch_failed", label=label, error=str(exc))
        return None


# Component weights
ANALYST_WEIGHT = 40
PRICE_TARGET_WEIGHT = 30
SENTIMENT_WEIGHT = 20
EARNINGS_WEIGHT = 10

# Display names for output
COMPONENT_NAMES = {
    "analyst": "Analyst Consensus",
    "price_target": "Price Target Upside",
    "sentiment": "News Sentiment",
    "earnings": "Earnings Proximity",
}


def create_conviction_score_tool(
    finnhub: FinnhubClient | None = None,
    alpha_vantage: AlphaVantageClient | None = None,
    fmp: FMPClient | None = None,
):
    @tool
    async def conviction_score(symbol: str) -> str:
        """Get a conviction score (0-100) for a stock symbol based on analyst consensus,
        price target upside, news sentiment, and earnings proximity. Use when the user
        asks about signal strength, conviction, or is evaluating a trade decision."""
        if not finnhub and not alpha_vantage and not fmp:
            return "Conviction score is not available — no data sources configured."

        # Parallel fetch all data
        tasks = []
        task_labels = []

        if finnhub:
            tasks.append(_safe_fetch(finnhub.get_quote(symbol), "quote"))
            task_labels.append("quote")
            tasks.append(_safe_fetch(finnhub.get_analyst_recommendations(symbol), "analyst"))
            task_labels.append("analyst")
            tasks.append(_safe_fetch(finnhub.get_earnings_calendar(symbol), "earnings"))
            task_labels.append("earnings")

        if alpha_vantage:
            tasks.append(_safe_fetch(alpha_vantage.get_news_sentiment(symbol), "news"))
            task_labels.append("news")

        if fmp:
            tasks.append(_safe_fetch(fmp.get_price_target_consensus(symbol), "pt_consensus"))
            task_labels.append("pt_consensus")

        results = await asyncio.gather(*tasks)
        data = dict(zip(task_labels, results))

        # Get market price
        quote = data.get("quote")
        market_price = quote.get("c", 0) if quote else 0

        # Compute sub-scores
        components = []
        missing = []

        # Analyst
        analyst_score, analyst_expl = compute_analyst_score(data.get("analyst"))
        if analyst_score is not None:
            components.append(("analyst", analyst_score, analyst_expl, ANALYST_WEIGHT))
        else:
            missing.append("Analyst Consensus")

        # Price target
        pt_score, pt_expl = compute_price_target_score(data.get("pt_consensus"), market_price)
        if pt_score is not None:
            components.append(("price_target", pt_score, pt_expl, PRICE_TARGET_WEIGHT))
        else:
            missing.append("Price Target Upside")

        # Sentiment
        sent_score, sent_expl = compute_sentiment_score(data.get("news"))
        if sent_score is not None:
            components.append(("sentiment", sent_score, sent_expl, SENTIMENT_WEIGHT))
        else:
            missing.append("News Sentiment")

        # Earnings (always returns a score)
        earn_score, earn_expl = compute_earnings_score(data.get("earnings"))
        components.append(("earnings", earn_score, earn_expl, EARNINGS_WEIGHT))

        # Composite
        composite, label, details = compute_composite(components)

        if composite is None:
            return f"Conviction score for {symbol}: Insufficient data to compute score."

        # Format output
        lines = [
            f"Conviction Score: {symbol}",
            "",
            f"  Score: {composite}/100 — {label}",
            "",
            "  Components:",
        ]

        for detail in details:
            display_name = COMPONENT_NAMES.get(detail["name"], detail["name"])
            lines.append(
                f"    {display_name + ':':25s} {detail['score']}/100 (weight {detail['weight']}%)  "
                f"— {detail['explanation']}"
            )

        # Show missing components
        for name in missing:
            lines.append(f"    {name + ':':25s} N/A")

        # Data sources
        sources = []
        if finnhub:
            sources.append("Finnhub")
        if alpha_vantage:
            sources.append("Alpha Vantage")
        if fmp:
            sources.append("FMP")
        lines.append("")
        lines.append(f"  Data Sources: {', '.join(sources)}")
        if missing:
            lines.append(f"  Missing: {', '.join(missing)}")
        else:
            lines.append("  Missing: None")

        return "\n".join(lines)

    return conviction_score
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py::TestConvictionScoreTool -v`
Expected: PASS (all 4 tests)

**Step 5: Run full conviction score test suite**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_conviction_score.py -v`
Expected: PASS (all 32 tests)

**Step 6: Commit**

```bash
cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score
git add src/ghostfolio_agent/tools/conviction_score.py tests/unit/test_conviction_score.py
git commit -m "feat: add conviction_score LangChain tool with parallel data fetching"
```

---

### Task 6: Wire Into Agent

**Files:**
- Modify: `src/ghostfolio_agent/tools/__init__.py`
- Modify: `src/ghostfolio_agent/agent/graph.py`

**Step 1: Update `__init__.py`**

Add import and register the tool in `create_tools()`:

```python
# Add import
from ghostfolio_agent.tools.conviction_score import create_conviction_score_tool

# In create_tools(), add after stock_quote:
def create_tools(...) -> list:
    tools = [
        ...existing tools...,
        create_conviction_score_tool(finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp),
    ]
    return tools
```

**Step 2: Update system prompt in `graph.py`**

Add to the SYSTEM_PROMPT tool list:

```
- conviction_score: Get a 0-100 conviction score for any stock symbol — combines analyst consensus, price target upside, news sentiment, and earnings proximity into one composite signal with full breakdown. Use when the user asks about signal strength, conviction, or is evaluating a trade decision.
```

**Step 3: Run full test suite**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/ -v`
Expected: PASS (all tests including existing 90 + new conviction score tests)

**Step 4: Commit**

```bash
cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score
git add src/ghostfolio_agent/tools/__init__.py src/ghostfolio_agent/agent/graph.py
git commit -m "feat: wire conviction_score tool into agent"
```

---

### Task 7: Integrate Conviction Score into holding_detail Smart Summary

**Files:**
- Modify: `src/ghostfolio_agent/tools/holding_detail.py`
- Modify: `tests/unit/test_holding_detail.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_holding_detail.py`, in `TestSmartSummary`:

```python
    @pytest.mark.asyncio
    async def test_conviction_score_in_smart_summary(
        self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client
    ):
        """Full enrichment → Smart Summary includes Conviction Score line."""
        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=finnhub_client,
            alpha_vantage=alpha_vantage_client,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" in result
        assert "Conviction Score:" in result
        assert "/100" in result

    @pytest.mark.asyncio
    async def test_conviction_score_absent_without_enrichment(self, ghostfolio_client):
        """No 3rd party clients → no Conviction Score line."""
        tool = create_holding_detail_tool(ghostfolio_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Conviction Score:" not in result
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_holding_detail.py::TestSmartSummary::test_conviction_score_in_smart_summary tests/unit/test_holding_detail.py::TestSmartSummary::test_conviction_score_absent_without_enrichment -v`
Expected: FAIL — assertion error (no "Conviction Score:" in output yet)

**Step 3: Modify `_format_smart_summary` in `holding_detail.py`**

Add conviction score computation to the existing `_format_smart_summary` function. Import the scoring functions at the top of the file:

```python
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
```

At the beginning of `_format_smart_summary`, before the existing signal computation, add:

```python
    # Compute conviction score from available enrichment data
    conviction_components = []

    a_score, a_expl = compute_analyst_score(enrichment.get("analyst"))
    if a_score is not None:
        conviction_components.append(("analyst", a_score, a_expl, ANALYST_WEIGHT))

    pt_score, pt_expl = compute_price_target_score(enrichment.get("pt_consensus"), market_price)
    if pt_score is not None:
        conviction_components.append(("price_target", pt_score, pt_expl, PRICE_TARGET_WEIGHT))

    s_score, s_expl = compute_sentiment_score(enrichment.get("news"))
    if s_score is not None:
        conviction_components.append(("sentiment", s_score, s_expl, SENTIMENT_WEIGHT))

    e_score, e_expl = compute_earnings_score(enrichment.get("earnings"))
    conviction_components.append(("earnings", e_score, e_expl, EARNINGS_WEIGHT))

    composite, label, _ = compute_composite(conviction_components)
    if composite is not None:
        signals.append(f"  Conviction Score: {composite}/100 — {label}")
```

This inserts the conviction score as the first signal line (before implied upside, analyst signal, etc.) since `signals` is empty at that point.

**Step 4: Run tests to verify they pass**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/test_holding_detail.py -v`
Expected: PASS (all existing + 2 new tests)

**Step 5: Run full test suite**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/ -v`
Expected: PASS (all tests)

**Step 6: Commit**

```bash
cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score
git add src/ghostfolio_agent/tools/holding_detail.py tests/unit/test_holding_detail.py
git commit -m "feat: embed conviction score in holding_detail Smart Summary"
```

---

### Task 8: Final Verification & Docs

**Step 1: Run full test suite one final time**

Run: `cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score && uv run pytest tests/unit/ -v`
Expected: ALL PASS

**Step 2: Update MEMORY.md**

Add a section about the conviction score tool to the project memory.

**Step 3: Commit docs**

```bash
cd /Users/ivanma/Desktop/gauntlet/AgentForge/.worktrees/conviction-score
git add -A
git commit -m "docs: add conviction score to project memory and plans"
```
