import pytest
from unittest.mock import AsyncMock, MagicMock

from ghostfolio_agent.tools.holding_detail import create_holding_detail_tool


# --- Mock data ---

LOOKUP_RESPONSE = {"items": [{"dataSource": "YAHOO", "symbol": "AAPL", "currency": "USD"}]}

HOLDING_RESPONSE = {
    "name": "Apple Inc.",
    "quantity": 50,
    "marketPrice": 195.50,
    "currency": "USD",
    "averagePrice": 150.00,
    "investment": 7500.00,
    "value": 9775.00,
    "netPerformance": 2275.00,
    "netPerformancePercent": 0.3033,
    "dividend": 125.00,
    "firstBuyDate": "2023-06-15",
    "transactionCount": 3,
}

EARNINGS_MOCK = [
    {"date": "2026-04-25", "epsEstimate": 2.35, "epsActual": None, "symbol": "AAPL"}
]

ANALYST_MOCK = [
    {"period": "2026-03-01", "strongBuy": 12, "buy": 18, "hold": 6, "sell": 1, "strongSell": 0}
]

CONGRESSIONAL_MOCK = [
    {
        "symbol": "AAPL",
        "transactionDate": "2026-02-10",
        "transactionAmount": "$1,001 - $15,000",
        "transactionType": "Purchase",
        "representative": "Nancy Pelosi",
    }
]

NEWS_MOCK = [
    {
        "title": "Apple beats earnings",
        "overall_sentiment_label": "Bullish",
        "overall_sentiment_score": "0.35",
        "time_published": "20260225T120000",
        "source": "Reuters",
    }
]

INSIDER_MOCK = [
    {
        "symbol": "AAPL",
        "transactionDate": "2026-02-15",
        "transactionType": "S-Sale",
        "securitiesTransacted": 50000,
        "price": 194.50,
        "reportingName": "Tim Cook",
    }
]


# --- Fixtures ---

@pytest.fixture
def ghostfolio_client():
    client = MagicMock()
    client.lookup_symbol = AsyncMock(return_value=LOOKUP_RESPONSE)
    client.get_holding = AsyncMock(return_value=HOLDING_RESPONSE)
    return client


@pytest.fixture
def finnhub_client():
    client = MagicMock()
    client.get_earnings_calendar = AsyncMock(return_value=EARNINGS_MOCK)
    client.get_analyst_recommendations = AsyncMock(return_value=ANALYST_MOCK)
    client.get_congressional_trading = AsyncMock(return_value=CONGRESSIONAL_MOCK)
    return client


@pytest.fixture
def alpha_vantage_client():
    client = MagicMock()
    client.get_news_sentiment = AsyncMock(return_value=NEWS_MOCK)
    return client


@pytest.fixture
def fmp_client():
    client = MagicMock()
    client.get_insider_trading = AsyncMock(return_value=INSIDER_MOCK)
    return client


# --- Tests ---

class TestBasicHolding:
    @pytest.mark.asyncio
    async def test_returns_basic_holding_data(self, ghostfolio_client):
        """Ghostfolio-only — core fields are present in output."""
        tool = create_holding_detail_tool(ghostfolio_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Apple Inc." in result
        assert "AAPL" in result
        assert "50" in result
        assert "195.50" in result
        assert "150.00" in result
        assert "7,500.00" in result
        assert "9,775.00" in result
        assert "2,275.00" in result
        assert "2023-06-15" in result
        assert "3" in result

    @pytest.mark.asyncio
    async def test_symbol_not_found(self, ghostfolio_client):
        """Empty lookup returns an error message."""
        ghostfolio_client.lookup_symbol = AsyncMock(return_value={"items": []})
        tool = create_holding_detail_tool(ghostfolio_client)
        result = await tool.ainvoke({"symbol": "ZZZZ"})

        assert "Could not find" in result or "not found" in result.lower()


class TestEnrichmentSections:
    @pytest.mark.asyncio
    async def test_includes_earnings_section(self, ghostfolio_client, finnhub_client):
        """Finnhub earnings data appears in output."""
        tool = create_holding_detail_tool(ghostfolio_client, finnhub=finnhub_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Earnings" in result
        assert "2026-04-25" in result
        assert "2.35" in result

    @pytest.mark.asyncio
    async def test_includes_analyst_section(self, ghostfolio_client, finnhub_client):
        """Finnhub analyst recommendations appear in output."""
        tool = create_holding_detail_tool(ghostfolio_client, finnhub=finnhub_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Analyst" in result
        # strong buy count
        assert "12" in result
        # buy count
        assert "18" in result

    @pytest.mark.asyncio
    async def test_includes_congressional_section(self, ghostfolio_client, finnhub_client):
        """Finnhub congressional trades appear in output."""
        tool = create_holding_detail_tool(ghostfolio_client, finnhub=finnhub_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Congressional" in result
        assert "Nancy Pelosi" in result
        assert "Purchase" in result

    @pytest.mark.asyncio
    async def test_includes_news_sentiment_section(self, ghostfolio_client, alpha_vantage_client):
        """Alpha Vantage news sentiment appears in output."""
        tool = create_holding_detail_tool(ghostfolio_client, alpha_vantage=alpha_vantage_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "News" in result or "Sentiment" in result
        assert "Apple beats earnings" in result
        assert "Bullish" in result

    @pytest.mark.asyncio
    async def test_includes_insider_trading_section(self, ghostfolio_client, fmp_client):
        """FMP insider trades appear in output."""
        tool = create_holding_detail_tool(ghostfolio_client, fmp=fmp_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Insider" in result
        assert "Tim Cook" in result
        assert "S-Sale" in result

    @pytest.mark.asyncio
    async def test_full_enrichment_all_sections_present(
        self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client
    ):
        """All 3 clients provided — all enrichment sections present."""
        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=finnhub_client,
            alpha_vantage=alpha_vantage_client,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        # Core
        assert "Apple Inc." in result
        # Finnhub sections
        assert "Earnings" in result
        assert "Analyst" in result
        assert "Congressional" in result
        # Alpha Vantage
        assert "News" in result or "Sentiment" in result
        # FMP
        assert "Insider" in result


class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_finnhub_error_still_returns_holding(self, ghostfolio_client):
        """Finnhub raises an exception — core holding data still returned."""
        bad_finnhub = MagicMock()
        bad_finnhub.get_earnings_calendar = AsyncMock(side_effect=RuntimeError("Finnhub down"))
        bad_finnhub.get_analyst_recommendations = AsyncMock(side_effect=RuntimeError("Finnhub down"))
        bad_finnhub.get_congressional_trading = AsyncMock(side_effect=RuntimeError("Finnhub down"))

        tool = create_holding_detail_tool(ghostfolio_client, finnhub=bad_finnhub)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Apple Inc." in result
        assert "AAPL" in result
        # Sections should be absent (or at least the tool should not crash)
        assert "Finnhub down" not in result

    @pytest.mark.asyncio
    async def test_all_3rd_party_errors_still_returns_holding(self, ghostfolio_client):
        """All 3 external clients error — core Ghostfolio data still returned."""
        bad_finnhub = MagicMock()
        bad_finnhub.get_earnings_calendar = AsyncMock(side_effect=RuntimeError("Finnhub down"))
        bad_finnhub.get_analyst_recommendations = AsyncMock(side_effect=RuntimeError("Finnhub down"))
        bad_finnhub.get_congressional_trading = AsyncMock(side_effect=RuntimeError("Finnhub down"))

        bad_av = MagicMock()
        bad_av.get_news_sentiment = AsyncMock(side_effect=RuntimeError("AV down"))

        bad_fmp = MagicMock()
        bad_fmp.get_insider_trading = AsyncMock(side_effect=RuntimeError("FMP down"))

        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=bad_finnhub,
            alpha_vantage=bad_av,
            fmp=bad_fmp,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Apple Inc." in result
        assert "9,775.00" in result
        # No raw exception messages leaked
        assert "down" not in result.lower()

    @pytest.mark.asyncio
    async def test_partial_enrichment_on_mixed_errors(
        self, ghostfolio_client, fmp_client
    ):
        """Finnhub errors, FMP works — FMP insider section present, Finnhub sections absent."""
        bad_finnhub = MagicMock()
        bad_finnhub.get_earnings_calendar = AsyncMock(side_effect=RuntimeError("Finnhub down"))
        bad_finnhub.get_analyst_recommendations = AsyncMock(side_effect=RuntimeError("Finnhub down"))
        bad_finnhub.get_congressional_trading = AsyncMock(side_effect=RuntimeError("Finnhub down"))

        bad_av = MagicMock()
        bad_av.get_news_sentiment = AsyncMock(side_effect=RuntimeError("AV down"))

        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=bad_finnhub,
            alpha_vantage=bad_av,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        # FMP worked
        assert "Insider" in result
        assert "Tim Cook" in result
        # Finnhub did not work — earnings section absent
        assert "2026-04-25" not in result
        assert "Nancy Pelosi" not in result
