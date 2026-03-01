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
