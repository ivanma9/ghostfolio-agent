"""Tests for alert result to AlertItem conversion."""

import pytest
from ghostfolio_agent.alerts.engine import AlertResult
from ghostfolio_agent.models.api import AlertItem
from ghostfolio_agent.api.chat import _ALERT_SEVERITY


class TestAlertSeverityMapping:
    def test_earnings_is_warning(self):
        assert _ALERT_SEVERITY["earnings_proximity"] == "warning"

    def test_big_mover_is_warning(self):
        assert _ALERT_SEVERITY["big_mover"] == "warning"

    def test_low_conviction_is_critical(self):
        assert _ALERT_SEVERITY["low_conviction"] == "critical"

    def test_analyst_downgrade_is_critical(self):
        assert _ALERT_SEVERITY["analyst_downgrade"] == "critical"

    def test_congressional_trade_is_warning(self):
        assert _ALERT_SEVERITY["congressional_trade"] == "warning"

    def test_unknown_defaults_to_warning(self):
        assert _ALERT_SEVERITY.get("unknown_condition", "warning") == "warning"


class TestAlertResultToAlertItem:
    def test_converts_warning_alert(self):
        result = AlertResult(symbol="AAPL", condition="earnings_proximity", message="AAPL earnings in 2 days")
        item = AlertItem(
            symbol=result.symbol,
            condition=result.condition,
            message=result.message,
            severity=_ALERT_SEVERITY.get(result.condition, "warning"),
        )
        assert item.symbol == "AAPL"
        assert item.condition == "earnings_proximity"
        assert item.severity == "warning"

    def test_converts_critical_alert(self):
        result = AlertResult(symbol="NVDA", condition="low_conviction", message="NVDA conviction dropped")
        item = AlertItem(
            symbol=result.symbol,
            condition=result.condition,
            message=result.message,
            severity=_ALERT_SEVERITY.get(result.condition, "warning"),
        )
        assert item.severity == "critical"

    def test_big_mover_severity(self):
        result = AlertResult(symbol="TSLA", condition="big_mover", message="TSLA up 6.2% today ($185.50) — significant daily move")
        item = AlertItem(
            symbol=result.symbol,
            condition=result.condition,
            message=result.message,
            severity=_ALERT_SEVERITY.get(result.condition, "warning"),
        )
        assert item.symbol == "TSLA"
        assert item.condition == "big_mover"
        assert item.severity == "warning"

    def test_analyst_downgrade_severity(self):
        result = AlertResult(symbol="MSFT", condition="analyst_downgrade", message="MSFT analyst consensus shifted to Sell")
        item = AlertItem(
            symbol=result.symbol,
            condition=result.condition,
            message=result.message,
            severity=_ALERT_SEVERITY.get(result.condition, "warning"),
        )
        assert item.severity == "critical"

    def test_congressional_trade_severity(self):
        result = AlertResult(symbol="AAPL", condition="congressional_trade", message="AAPL has 5 congressional trades")
        item = AlertItem(
            symbol=result.symbol,
            condition=result.condition,
            message=result.message,
            severity=_ALERT_SEVERITY.get(result.condition, "warning"),
        )
        assert item.severity == "warning"

    def test_unknown_condition_defaults_to_warning(self):
        result = AlertResult(symbol="XYZ", condition="unknown_condition", message="Some unknown alert")
        item = AlertItem(
            symbol=result.symbol,
            condition=result.condition,
            message=result.message,
            severity=_ALERT_SEVERITY.get(result.condition, "warning"),
        )
        assert item.severity == "warning"

    def test_message_preserved(self):
        msg = "AAPL earnings in 2 days (2026-03-03) — consider position sizing"
        result = AlertResult(symbol="AAPL", condition="earnings_proximity", message=msg)
        item = AlertItem(
            symbol=result.symbol,
            condition=result.condition,
            message=result.message,
            severity=_ALERT_SEVERITY.get(result.condition, "warning"),
        )
        assert item.message == msg
