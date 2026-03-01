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


from unittest.mock import MagicMock, AsyncMock
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient


HOLDINGS_RESPONSE = {
    "holdings": {
        "AAPL": {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "quantity": 10,
            "marketPrice": 200.0,
            "valueInBaseCurrency": 2000.0,
            "allocationInPercentage": 0.4,
        },
        "NVDA": {
            "symbol": "NVDA",
            "name": "NVIDIA Corp",
            "quantity": 5,
            "marketPrice": 900.0,
            "valueInBaseCurrency": 4500.0,
            "allocationInPercentage": 0.45,
        },
        "MSFT": {
            "symbol": "MSFT",
            "name": "Microsoft Corp",
            "quantity": 8,
            "marketPrice": 400.0,
            "valueInBaseCurrency": 3200.0,
            "allocationInPercentage": 0.15,
        },
    }
}

QUOTE_AAPL = {"c": 200.0, "dp": -5.0, "d": -10.0}
QUOTE_NVDA = {"c": 900.0, "dp": 3.2, "d": 28.8}
QUOTE_MSFT = {"c": 400.0, "dp": 0.5, "d": 2.0}

EARNINGS_AAPL = [{"date": "2026-03-05", "epsEstimate": 2.1, "epsActual": None, "symbol": "AAPL"}]
EARNINGS_NVDA = []
EARNINGS_MSFT = []

ANALYST_AAPL = [{"strongBuy": 10, "buy": 15, "hold": 5, "sell": 1, "strongSell": 0, "period": "2026-02-01"}]

NEWS_AAPL = [
    {"overall_sentiment_label": "Bearish", "title": "Apple faces headwinds", "source": "Reuters"},
    {"overall_sentiment_label": "Somewhat_Bearish", "title": "Apple warns on supply", "source": "Bloomberg"},
]

PT_CONSENSUS_AAPL = [{"targetConsensus": 230.0, "targetHigh": 280.0, "targetLow": 180.0}]

MACRO_FED = {"data": [{"date": "2026-01-29", "value": "4.50"}]}
MACRO_CPI = {"data": [{"date": "2026-01-15", "value": "2.80"}]}
MACRO_TREASURY = {"data": [{"date": "2026-02-27", "value": "4.25"}]}


@pytest.fixture
def ghostfolio_client():
    client = MagicMock(spec=GhostfolioClient)
    client.get_portfolio_holdings = AsyncMock(return_value=HOLDINGS_RESPONSE)
    return client


@pytest.fixture
def finnhub_client():
    client = MagicMock(spec=FinnhubClient)

    async def mock_quote(symbol):
        return {"AAPL": QUOTE_AAPL, "NVDA": QUOTE_NVDA, "MSFT": QUOTE_MSFT}.get(symbol, {"c": 0, "dp": 0, "d": 0})

    async def mock_earnings(symbol):
        return {"AAPL": EARNINGS_AAPL, "NVDA": EARNINGS_NVDA, "MSFT": EARNINGS_MSFT}.get(symbol, [])

    async def mock_analyst(symbol):
        return {"AAPL": ANALYST_AAPL}.get(symbol, [])

    client.get_quote = MagicMock(side_effect=mock_quote)
    client.get_earnings_calendar = MagicMock(side_effect=mock_earnings)
    client.get_analyst_recommendations = MagicMock(side_effect=mock_analyst)
    return client


@pytest.fixture
def alpha_vantage_client():
    client = MagicMock(spec=AlphaVantageClient)

    async def mock_news(ticker):
        return {"AAPL": NEWS_AAPL}.get(ticker, [])

    async def mock_fed():
        return MACRO_FED

    async def mock_cpi():
        return MACRO_CPI

    async def mock_treasury(maturity="10year"):
        return MACRO_TREASURY

    client.get_news_sentiment = MagicMock(side_effect=mock_news)
    client.get_fed_funds_rate = MagicMock(side_effect=mock_fed)
    client.get_cpi = MagicMock(side_effect=mock_cpi)
    client.get_treasury_yield = MagicMock(side_effect=mock_treasury)
    return client


@pytest.fixture
def fmp_client():
    client = MagicMock(spec=FMPClient)

    async def mock_pt(symbol):
        return {"AAPL": PT_CONSENSUS_AAPL}.get(symbol, [])

    client.get_price_target_consensus = MagicMock(side_effect=mock_pt)
    return client


class TestMorningBriefingTool:
    @pytest.mark.asyncio
    async def test_full_briefing(self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client):
        """Full briefing includes all 6 sections."""
        from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool, _macro_cache

        _macro_cache["data"] = None
        _macro_cache["fetched_at"] = None

        tool = create_morning_briefing_tool(
            ghostfolio_client, finnhub=finnhub_client, alpha_vantage=alpha_vantage_client, fmp=fmp_client
        )
        result = await tool.ainvoke({})

        assert "Portfolio Overview" in result
        assert "$9,700.00" in result
        assert "Top Movers" in result
        assert "AAPL" in result
        assert "Earnings Watch" in result
        assert "Market Signals" in result
        assert "Macro Snapshot" in result
        assert "4.50" in result
        assert "2.80" in result
        assert "Action Items" in result

    @pytest.mark.asyncio
    async def test_empty_portfolio(self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client):
        """Empty portfolio returns a helpful message."""
        from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool

        ghostfolio_client.get_portfolio_holdings = AsyncMock(return_value={"holdings": {}})
        tool = create_morning_briefing_tool(
            ghostfolio_client, finnhub=finnhub_client, alpha_vantage=alpha_vantage_client, fmp=fmp_client
        )
        result = await tool.ainvoke({})
        assert "no holdings" in result.lower()

    @pytest.mark.asyncio
    async def test_no_external_clients(self, ghostfolio_client):
        """Briefing works with only Ghostfolio client (degraded)."""
        from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool

        tool = create_morning_briefing_tool(ghostfolio_client)
        result = await tool.ainvoke({})
        assert "Portfolio Overview" in result

    @pytest.mark.asyncio
    async def test_macro_cache_used_on_second_call(self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client):
        """Second briefing call reuses cached macro data."""
        from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool, _macro_cache

        _macro_cache["data"] = None
        _macro_cache["fetched_at"] = None

        tool = create_morning_briefing_tool(
            ghostfolio_client, finnhub=finnhub_client, alpha_vantage=alpha_vantage_client, fmp=fmp_client
        )
        await tool.ainvoke({})

        alpha_vantage_client.get_fed_funds_rate.reset_mock()
        alpha_vantage_client.get_cpi.reset_mock()
        alpha_vantage_client.get_treasury_yield.reset_mock()

        await tool.ainvoke({})

        alpha_vantage_client.get_fed_funds_rate.assert_not_called()
        alpha_vantage_client.get_cpi.assert_not_called()
        alpha_vantage_client.get_treasury_yield.assert_not_called()
