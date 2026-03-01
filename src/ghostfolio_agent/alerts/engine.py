"""AlertEngine — detects notable portfolio conditions and enforces per-key cooldowns."""

import time
from datetime import date
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

COOLDOWN_TTL = 86400  # 24 hours in seconds


class AlertEngine:
    """Checks portfolio holdings for notable conditions with cooldown suppression."""

    def __init__(self) -> None:
        # Maps alert key → unix timestamp when it was last fired
        self._fired: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Cooldown helpers
    # ------------------------------------------------------------------

    def _is_cooled_down(self, key: str) -> bool:
        """Return True if the alert key has passed its cooldown period (ready to fire)."""
        fired_at = self._fired.get(key)
        if fired_at is None:
            return True
        return (time.time() - fired_at) > COOLDOWN_TTL

    def _record(self, key: str) -> None:
        """Mark an alert key as fired now, and prune expired entries."""
        now = time.time()
        self._fired[key] = now
        # Prune entries older than COOLDOWN_TTL
        expired = [k for k, ts in self._fired.items() if (now - ts) >= COOLDOWN_TTL]
        for k in expired:
            del self._fired[k]

    # ------------------------------------------------------------------
    # Alert condition functions
    # ------------------------------------------------------------------

    def _check_earnings_proximity(
        self,
        symbol: str,
        earnings_data: list[dict] | None,
        today: date,
    ) -> str | None:
        """Alert if earnings are within 3 days (inclusive)."""
        if not earnings_data:
            return None
        for entry in earnings_data:
            date_str = entry.get("date", "")
            try:
                earnings_date = date.fromisoformat(date_str)
                days_until = (earnings_date - today).days
                if 0 <= days_until <= 3:
                    return (
                        f"{symbol} earnings in {days_until} days ({date_str})"
                        " — consider position sizing"
                    )
            except (ValueError, TypeError):
                continue
        return None

    def _check_big_mover(
        self,
        symbol: str,
        quote_data: dict | None,
    ) -> str | None:
        """Alert if |daily % change| >= 5.0."""
        if not quote_data:
            return None
        dp = quote_data.get("dp", 0.0) or 0.0
        price = quote_data.get("c", 0.0) or 0.0
        if abs(dp) < 5.0:
            return None
        direction = "up" if dp > 0 else "down"
        return (
            f"{symbol} {direction} {abs(dp):.1f}% today (${price:.2f})"
            " — significant daily move"
        )

    def _check_analyst_downgrade(
        self,
        symbol: str,
        analyst_data: list[dict] | None,
    ) -> str | None:
        """Alert if bearish (sell + strongSell) >= 50% of total analysts."""
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
        if bearish / total < 0.5:
            return None
        bullish = strong_buy + buy
        return (
            f"{symbol} analyst consensus shifted to Sell"
            f" ({bullish} of {total} analysts bullish) — monitor closely"
        )

    def _check_low_conviction(
        self,
        symbol: str,
        analyst_data: list[dict] | None,
        pt_data: list[dict] | None,
        news_data: list[dict] | None,
        earnings_data: list[dict] | None,
        market_price: float,
    ) -> str | None:
        """Alert if composite conviction score < 40."""
        components = []

        analyst_score, analyst_expl = compute_analyst_score(analyst_data)
        if analyst_score is not None:
            components.append(("analyst", analyst_score, analyst_expl, ANALYST_WEIGHT))

        pt_score, pt_expl = compute_price_target_score(pt_data, market_price)
        if pt_score is not None:
            components.append(("price_target", pt_score, pt_expl, PRICE_TARGET_WEIGHT))

        sent_score, sent_expl = compute_sentiment_score(news_data)
        if sent_score is not None:
            components.append(("sentiment", sent_score, sent_expl, SENTIMENT_WEIGHT))

        earn_score, earn_expl = compute_earnings_score(earnings_data)
        components.append(("earnings", earn_score, earn_expl, EARNINGS_WEIGHT))

        # Need at least one non-earnings component
        non_earnings = [c for c in components if c[0] != "earnings"]
        if not non_earnings:
            return None

        composite, label, _ = compute_composite(components)
        if composite is None or composite >= 40:
            return None

        return (
            f"{symbol} conviction score dropped to {composite}/100 ({label})"
            " — review position"
        )
