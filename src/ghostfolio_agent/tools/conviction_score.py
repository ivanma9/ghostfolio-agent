"""Conviction Score — composite 0-100 score from multiple market signals."""

from datetime import date


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
