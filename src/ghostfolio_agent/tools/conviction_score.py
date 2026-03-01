"""Conviction Score — composite 0-100 score from multiple market signals."""

import asyncio
import structlog
from langchain_core.tools import tool
from ghostfolio_agent.tools.cache import ttl_cache
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient
from datetime import date

logger = structlog.get_logger()


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
    @ttl_cache(ttl=300)
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
