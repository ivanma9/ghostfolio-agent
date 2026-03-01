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
        cache = {"data": None, "fetched_at": None}
        assert is_macro_cache_valid(cache) is False

    def test_fresh_cache_is_valid(self):
        cache = {"data": {"fed_funds_rate": 4.5}, "fetched_at": time.time()}
        assert is_macro_cache_valid(cache) is True

    def test_stale_cache_is_invalid(self):
        cache = {"data": {"fed_funds_rate": 4.5}, "fetched_at": time.time() - MACRO_CACHE_TTL - 1}
        assert is_macro_cache_valid(cache) is False


class TestGenerateActionItems:
    def test_low_conviction(self):
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
        earnings = [{"symbol": "AAPL", "name": "Apple", "earnings_date": "2026-03-05", "days_until": 5}]
        items = generate_action_items([], earnings, [])
        assert any("AAPL" in item and "5 days" in item for item in items)

    def test_big_mover_down(self):
        movers = [{"symbol": "NVDA", "name": "NVIDIA", "daily_change": -5.2, "direction": "down"}]
        items = generate_action_items([], [], movers)
        assert any("NVDA" in item and "5.2%" in item for item in items)

    def test_no_flags_no_items(self):
        items = generate_action_items([], [], [])
        assert items == []
