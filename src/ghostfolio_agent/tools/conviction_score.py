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
