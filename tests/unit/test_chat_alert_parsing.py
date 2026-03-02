"""Tests for parsing alert strings into structured AlertItems."""

import pytest
from ghostfolio_agent.api.chat import _parse_alert_strings


class TestParseAlertStrings:
    def test_earnings_alert(self):
        items = _parse_alert_strings([
            "AAPL earnings in 2 days (2026-03-03) — consider position sizing"
        ])
        assert len(items) == 1
        assert items[0].symbol == "AAPL"
        assert items[0].condition == "earnings_proximity"
        assert items[0].severity == "warning"

    def test_big_mover_alert(self):
        items = _parse_alert_strings([
            "TSLA up 6.2% today ($185.50) — significant daily move"
        ])
        assert len(items) == 1
        assert items[0].symbol == "TSLA"
        assert items[0].condition == "big_mover"
        assert items[0].severity == "warning"

    def test_low_conviction_alert(self):
        items = _parse_alert_strings([
            "NVDA conviction score dropped to 25/100 (Sell) — review position"
        ])
        assert len(items) == 1
        assert items[0].symbol == "NVDA"
        assert items[0].condition == "low_conviction"
        assert items[0].severity == "critical"

    def test_analyst_downgrade_alert(self):
        items = _parse_alert_strings([
            "MSFT analyst consensus shifted to Sell (3 of 20 analysts bullish) — monitor closely"
        ])
        assert len(items) == 1
        assert items[0].symbol == "MSFT"
        assert items[0].condition == "analyst_downgrade"
        assert items[0].severity == "critical"

    def test_congressional_trade_alert(self):
        items = _parse_alert_strings([
            "AAPL has 5 congressional trades in the last 3 days (3 buys, 2 sells) — Bullish"
        ])
        assert len(items) == 1
        assert items[0].symbol == "AAPL"
        assert items[0].condition == "congressional_trade"
        assert items[0].severity == "warning"

    def test_multiple_alerts(self):
        items = _parse_alert_strings([
            "AAPL earnings in 1 days (2026-03-02) — consider position sizing",
            "TSLA conviction score dropped to 30/100 (Sell) — review position",
        ])
        assert len(items) == 2
        assert items[0].severity == "warning"
        assert items[1].severity == "critical"

    def test_empty_list(self):
        items = _parse_alert_strings([])
        assert items == []

    def test_unrecognized_alert_uses_fallback(self):
        items = _parse_alert_strings(["UNKNOWN some weird alert text"])
        assert len(items) == 1
        assert items[0].symbol == "UNKNOWN"
        assert items[0].condition == "unknown"
        assert items[0].severity == "warning"
