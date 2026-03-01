"""Tests for AlertEngine — cooldown logic, condition checks, low conviction."""

import time
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from ghostfolio_agent.alerts.engine import (
    AlertEngine,
    COOLDOWN_TTL,
)
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient


# ---------------------------------------------------------------------------
# Task 1 — Cooldown Logic
# ---------------------------------------------------------------------------

class TestCooldown:
    def setup_method(self):
        self.engine = AlertEngine()

    def test_new_alert_is_cooled_down(self):
        """Fresh engine — never-fired key is ready to fire."""
        assert self.engine._is_cooled_down("AAPL:earnings") is True

    def test_fired_alert_is_not_cooled_down(self):
        """After _record(), same key is suppressed within TTL."""
        self.engine._record("AAPL:earnings")
        assert self.engine._is_cooled_down("AAPL:earnings") is False

    def test_different_alert_key_not_affected(self):
        """Recording one key does not affect an independent key."""
        self.engine._record("AAPL:earnings")
        assert self.engine._is_cooled_down("MSFT:big_mover") is True

    def test_expired_alert_passes_cooldown(self):
        """An entry older than COOLDOWN_TTL is ready to fire again."""
        self.engine._fired["AAPL:earnings"] = time.time() - COOLDOWN_TTL - 1
        assert self.engine._is_cooled_down("AAPL:earnings") is True

    def test_record_prunes_old_entries(self):
        """_record() removes entries older than COOLDOWN_TTL from _fired."""
        old_key = "TSLA:old"
        self.engine._fired[old_key] = time.time() - COOLDOWN_TTL - 100
        # Fire any new alert to trigger pruning
        self.engine._record("NVDA:earnings")
        assert old_key not in self.engine._fired


# ---------------------------------------------------------------------------
# Task 2 — Alert Condition Functions
# ---------------------------------------------------------------------------

class TestCheckEarningsProximity:
    def setup_method(self):
        self.engine = AlertEngine()
        self.today = date(2026, 2, 28)

    def _earnings(self, days_ahead: int) -> list[dict]:
        d = self.today + timedelta(days=days_ahead)
        return [{"date": d.isoformat()}]

    def test_2_days_triggers(self):
        result = self.engine._check_earnings_proximity("AAPL", self._earnings(2), self.today)
        assert result is not None
        assert "AAPL" in result
        assert "2 days" in result

    def test_3_days_triggers(self):
        result = self.engine._check_earnings_proximity("AAPL", self._earnings(3), self.today)
        assert result is not None
        assert "3 days" in result

    def test_4_days_does_not_trigger(self):
        result = self.engine._check_earnings_proximity("AAPL", self._earnings(4), self.today)
        assert result is None

    def test_empty_earnings_returns_none(self):
        result = self.engine._check_earnings_proximity("AAPL", [], self.today)
        assert result is None

    def test_none_earnings_returns_none(self):
        result = self.engine._check_earnings_proximity("AAPL", None, self.today)
        assert result is None


class TestCheckBigMover:
    def setup_method(self):
        self.engine = AlertEngine()

    def test_negative_5_pct_triggers(self):
        quote = {"dp": -5.0, "c": 150.0}
        result = self.engine._check_big_mover("AAPL", quote)
        assert result is not None
        assert "AAPL" in result
        assert "down" in result
        assert "5.0%" in result

    def test_positive_6_3_pct_triggers(self):
        quote = {"dp": 6.3, "c": 200.0}
        result = self.engine._check_big_mover("AAPL", quote)
        assert result is not None
        assert "up" in result
        assert "6.3%" in result

    def test_4_9_pct_does_not_trigger(self):
        quote = {"dp": 4.9, "c": 100.0}
        result = self.engine._check_big_mover("AAPL", quote)
        assert result is None

    def test_none_quote_returns_none(self):
        result = self.engine._check_big_mover("AAPL", None)
        assert result is None

    def test_zero_pct_returns_none(self):
        quote = {"dp": 0.0, "c": 100.0}
        result = self.engine._check_big_mover("AAPL", quote)
        assert result is None


class TestCheckAnalystDowngrade:
    def setup_method(self):
        self.engine = AlertEngine()

    def _analyst(self, strong_buy=0, buy=0, hold=0, sell=0, strong_sell=0):
        return [{
            "strongBuy": strong_buy,
            "buy": buy,
            "hold": hold,
            "sell": sell,
            "strongSell": strong_sell,
        }]

    def test_sell_consensus_triggers(self):
        # 3 sell + 2 strong_sell = 5 bearish out of 7 total → >50%
        data = self._analyst(strong_buy=0, buy=2, hold=0, sell=3, strong_sell=2)
        result = self.engine._check_analyst_downgrade("AAPL", data)
        assert result is not None
        assert "AAPL" in result
        assert "Sell" in result

    def test_buy_consensus_does_not_trigger(self):
        # Mostly bullish
        data = self._analyst(strong_buy=5, buy=3, hold=2, sell=1, strong_sell=0)
        result = self.engine._check_analyst_downgrade("AAPL", data)
        assert result is None

    def test_none_analyst_data_returns_none(self):
        result = self.engine._check_analyst_downgrade("AAPL", None)
        assert result is None

    def test_empty_analyst_data_returns_none(self):
        result = self.engine._check_analyst_downgrade("AAPL", [])
        assert result is None


# ---------------------------------------------------------------------------
# Task 3 — Low Conviction Check
# ---------------------------------------------------------------------------

class TestCheckLowConviction:
    def setup_method(self):
        self.engine = AlertEngine()

    def _bearish_analyst(self):
        return [{"strongBuy": 0, "buy": 1, "hold": 2, "sell": 5, "strongSell": 3}]

    def _bearish_news(self):
        return [
            {"overall_sentiment_label": "Bearish"},
            {"overall_sentiment_label": "Bearish"},
            {"overall_sentiment_label": "Bearish"},
        ]

    def _bullish_analyst(self):
        return [{"strongBuy": 8, "buy": 5, "hold": 2, "sell": 0, "strongSell": 0}]

    def _bullish_news(self):
        return [
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Bullish"},
        ]

    def _bullish_pt(self, target: float = 200.0):
        return [{"targetConsensus": target}]

    def _bearish_pt(self, target: float = 80.0):
        return [{"targetConsensus": target}]

    def test_bearish_data_triggers_low_conviction(self):
        result = self.engine._check_low_conviction(
            symbol="AAPL",
            analyst_data=self._bearish_analyst(),
            pt_data=self._bearish_pt(),
            news_data=self._bearish_news(),
            earnings_data=None,
            market_price=100.0,
        )
        assert result is not None
        assert "AAPL" in result
        assert "conviction score" in result.lower()

    def test_bullish_data_does_not_trigger(self):
        result = self.engine._check_low_conviction(
            symbol="AAPL",
            analyst_data=self._bullish_analyst(),
            pt_data=self._bullish_pt(),
            news_data=self._bullish_news(),
            earnings_data=None,
            market_price=100.0,
        )
        assert result is None

    def test_all_none_returns_none(self):
        result = self.engine._check_low_conviction(
            symbol="AAPL",
            analyst_data=None,
            pt_data=None,
            news_data=None,
            earnings_data=None,
            market_price=0.0,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Task 4 — check_alerts integration
# ---------------------------------------------------------------------------

HOLDINGS_RESPONSE = {
    "holdings": {
        "AAPL": {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "quantity": 10,
            "valueInBaseCurrency": 2000.0,
        },
        "TSLA": {
            "symbol": "TSLA",
            "name": "Tesla Inc.",
            "quantity": 5,
            "valueInBaseCurrency": 1000.0,
        },
    }
}


@pytest.fixture
def mock_ghostfolio():
    client = MagicMock(spec=GhostfolioClient)
    client.get_portfolio_holdings = AsyncMock(return_value=HOLDINGS_RESPONSE)
    return client


@pytest.fixture
def mock_finnhub():
    client = MagicMock(spec=FinnhubClient)
    today = date.today()
    earnings_date = (today + timedelta(days=2)).isoformat()

    async def mock_quote(symbol):
        return {
            "AAPL": {"c": 200.0, "dp": -6.0, "d": -12.0},
            "TSLA": {"c": 180.0, "dp": 1.0, "d": 1.8},
        }.get(symbol, {"c": 0, "dp": 0, "d": 0})

    async def mock_earnings(symbol):
        return {
            "TSLA": [{"date": earnings_date}],
        }.get(symbol, [])

    async def mock_analyst(symbol):
        return {
            "AAPL": [{"strongBuy": 1, "buy": 1, "hold": 2, "sell": 4, "strongSell": 3}],
        }.get(symbol, [])

    client.get_quote = MagicMock(side_effect=mock_quote)
    client.get_earnings_calendar = MagicMock(side_effect=mock_earnings)
    client.get_analyst_recommendations = MagicMock(side_effect=mock_analyst)
    return client


class TestCheckAlerts:
    @pytest.mark.asyncio
    async def test_finds_big_mover_and_earnings(self, mock_ghostfolio, mock_finnhub):
        engine = AlertEngine()
        alerts = await engine.check_alerts(mock_ghostfolio, finnhub=mock_finnhub)
        alert_text = "\n".join(alerts)
        assert "AAPL" in alert_text
        assert "TSLA" in alert_text

    @pytest.mark.asyncio
    async def test_cooldown_suppresses_repeat(self, mock_ghostfolio, mock_finnhub):
        engine = AlertEngine()
        alerts1 = await engine.check_alerts(mock_ghostfolio, finnhub=mock_finnhub)
        assert len(alerts1) > 0
        alerts2 = await engine.check_alerts(mock_ghostfolio, finnhub=mock_finnhub)
        assert len(alerts2) == 0

    @pytest.mark.asyncio
    async def test_no_clients_returns_empty(self, mock_ghostfolio):
        engine = AlertEngine()
        alerts = await engine.check_alerts(mock_ghostfolio)
        assert alerts == []

    @pytest.mark.asyncio
    async def test_empty_portfolio_returns_empty(self, mock_finnhub):
        client = MagicMock(spec=GhostfolioClient)
        client.get_portfolio_holdings = AsyncMock(return_value={"holdings": {}})
        engine = AlertEngine()
        alerts = await engine.check_alerts(client, finnhub=mock_finnhub)
        assert alerts == []

    @pytest.mark.asyncio
    async def test_holdings_fetch_failure_returns_empty(self, mock_finnhub):
        client = MagicMock(spec=GhostfolioClient)
        client.get_portfolio_holdings = AsyncMock(side_effect=Exception("API error"))
        engine = AlertEngine()
        alerts = await engine.check_alerts(client, finnhub=mock_finnhub)
        assert alerts == []
