"""Tests for structured alert items in ChatResponse."""

import pytest
from ghostfolio_agent.models.api import AlertItem, ChatResponse


class TestAlertItem:
    def test_alert_item_warning(self):
        item = AlertItem(
            symbol="AAPL",
            condition="earnings_proximity",
            message="AAPL earnings in 2 days",
            severity="warning",
        )
        assert item.symbol == "AAPL"
        assert item.severity == "warning"

    def test_alert_item_critical(self):
        item = AlertItem(
            symbol="TSLA",
            condition="low_conviction",
            message="TSLA conviction score dropped to 25/100",
            severity="critical",
        )
        assert item.severity == "critical"

    def test_alert_item_invalid_severity(self):
        with pytest.raises(Exception):
            AlertItem(
                symbol="X",
                condition="test",
                message="test",
                severity="invalid",
            )


class TestChatResponseAlerts:
    def test_chat_response_includes_alerts_field(self):
        resp = ChatResponse(
            response="Hello",
            session_id="s1",
            alerts=[
                AlertItem(symbol="AAPL", condition="big_mover", message="AAPL up 6%", severity="warning"),
            ],
        )
        assert len(resp.alerts) == 1
        assert resp.alerts[0].symbol == "AAPL"

    def test_chat_response_alerts_defaults_empty(self):
        resp = ChatResponse(response="Hi", session_id="s1")
        assert resp.alerts == []
