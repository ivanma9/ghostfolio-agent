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

NEWS_MOCK = [
    {
        "title": "Apple beats earnings",
        "overall_sentiment_label": "Bullish",
        "overall_sentiment_score": "0.35",
        "time_published": "20260225T120000",
        "source": "Reuters",
    }
]

PT_CONSENSUS_MOCK = [
    {
        "symbol": "AAPL",
        "targetHigh": 250.0,
        "targetLow": 180.0,
        "targetConsensus": 220.50,
        "targetMedian": 225.0,
    }
]

PT_SUMMARY_MOCK = [
    {
        "symbol": "AAPL",
        "lastMonthCount": 7,
        "lastMonthAvgPriceTarget": 218.0,
        "lastQuarterCount": 15,
        "lastQuarterAvgPriceTarget": 215.0,
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
    return client


@pytest.fixture
def alpha_vantage_client():
    client = MagicMock()
    client.get_news_sentiment = AsyncMock(return_value=NEWS_MOCK)
    return client


@pytest.fixture
def fmp_client():
    client = MagicMock()
    client.get_price_target_consensus = AsyncMock(return_value=PT_CONSENSUS_MOCK)
    client.get_price_target_summary = AsyncMock(return_value=PT_SUMMARY_MOCK)
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
    async def test_includes_news_sentiment_section(self, ghostfolio_client, alpha_vantage_client):
        """Alpha Vantage news sentiment appears in output."""
        tool = create_holding_detail_tool(ghostfolio_client, alpha_vantage=alpha_vantage_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "News" in result or "Sentiment" in result
        assert "Apple beats earnings" in result
        assert "Bullish" in result

    @pytest.mark.asyncio
    async def test_includes_price_targets_section(self, ghostfolio_client, fmp_client):
        """FMP price targets appear in output."""
        tool = create_holding_detail_tool(ghostfolio_client, fmp=fmp_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Price Targets" in result
        assert "220.50" in result
        assert "250.00" in result

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
        # Alpha Vantage
        assert "News" in result or "Sentiment" in result
        # FMP
        assert "Price Targets" in result


class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_finnhub_error_still_returns_holding(self, ghostfolio_client):
        """Finnhub raises an exception — core holding data still returned."""
        bad_finnhub = MagicMock()
        bad_finnhub.get_earnings_calendar = AsyncMock(side_effect=RuntimeError("Finnhub down"))
        bad_finnhub.get_analyst_recommendations = AsyncMock(side_effect=RuntimeError("Finnhub down"))

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

        bad_av = MagicMock()
        bad_av.get_news_sentiment = AsyncMock(side_effect=RuntimeError("AV down"))

        bad_fmp = MagicMock()
        bad_fmp.get_price_target_consensus = AsyncMock(side_effect=RuntimeError("FMP down"))
        bad_fmp.get_price_target_summary = AsyncMock(side_effect=RuntimeError("FMP down"))

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
        """Finnhub errors, FMP works — FMP price targets present, Finnhub sections absent."""
        bad_finnhub = MagicMock()
        bad_finnhub.get_earnings_calendar = AsyncMock(side_effect=RuntimeError("Finnhub down"))
        bad_finnhub.get_analyst_recommendations = AsyncMock(side_effect=RuntimeError("Finnhub down"))

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
        assert "Price Targets" in result
        assert "220.50" in result
        # Finnhub did not work — earnings section absent
        assert "2026-04-25" not in result
        assert "Nancy Pelosi" not in result


class TestSmartSummary:
    @pytest.mark.asyncio
    async def test_implied_upside_displayed(self, ghostfolio_client, fmp_client):
        """market=195.50, consensus=220.50 → '+12.8%' shown in Smart Summary."""
        tool = create_holding_detail_tool(ghostfolio_client, fmp=fmp_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" in result
        assert "Implied Upside" in result
        assert "+12.8%" in result

    @pytest.mark.asyncio
    async def test_analyst_signal_strong_buy(self, ghostfolio_client, finnhub_client):
        """12 strongBuy + 18 buy = 30 bullish of 37 → 'Strong Buy' '30 of 37'."""
        tool = create_holding_detail_tool(ghostfolio_client, finnhub=finnhub_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" in result
        assert "Analyst Signal" in result
        assert "Strong Buy" in result
        assert "30 of 37" in result

    @pytest.mark.asyncio
    async def test_sentiment_score_bullish(self, ghostfolio_client, alpha_vantage_client):
        """1 Bullish article → 'Bullish' '1 of 1' in Smart Summary."""
        tool = create_holding_detail_tool(ghostfolio_client, alpha_vantage=alpha_vantage_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" in result
        assert "Sentiment" in result
        assert "Bullish" in result
        assert "1 of 1" in result

    @pytest.mark.asyncio
    async def test_earnings_proximity_flag(self, ghostfolio_client):
        """Earnings 8 days away → 'Earnings Alert' '8 days'."""
        from datetime import date, timedelta
        near_date = (date.today() + timedelta(days=8)).isoformat()
        near_earnings = [{"date": near_date, "epsEstimate": 2.35, "epsActual": None, "symbol": "AAPL"}]

        finnhub = MagicMock()
        finnhub.get_earnings_calendar = AsyncMock(return_value=near_earnings)
        finnhub.get_analyst_recommendations = AsyncMock(return_value=None)

        tool = create_holding_detail_tool(ghostfolio_client, finnhub=finnhub)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" in result
        assert "Earnings Alert" in result
        assert "8 days" in result

    @pytest.mark.asyncio
    async def test_no_earnings_proximity_when_far(self, ghostfolio_client):
        """Earnings 45 days away → no 'Earnings Alert'."""
        from datetime import date, timedelta
        far_date = (date.today() + timedelta(days=45)).isoformat()
        far_earnings = [{"date": far_date, "epsEstimate": 2.35, "epsActual": None, "symbol": "AAPL"}]

        finnhub = MagicMock()
        finnhub.get_earnings_calendar = AsyncMock(return_value=far_earnings)
        finnhub.get_analyst_recommendations = AsyncMock(return_value=None)

        tool = create_holding_detail_tool(ghostfolio_client, finnhub=finnhub)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Earnings Alert" not in result

    @pytest.mark.asyncio
    async def test_implied_downside_when_target_below_price(self, ghostfolio_client):
        """consensus=170, market=195.50 → 'Implied Downside' '-13.0%'."""
        fmp = MagicMock()
        fmp.get_price_target_consensus = AsyncMock(return_value=[{
            "symbol": "AAPL",
            "targetHigh": 200.0,
            "targetLow": 150.0,
            "targetConsensus": 170.0,
            "targetMedian": 175.0,
        }])
        fmp.get_price_target_summary = AsyncMock(return_value=None)

        tool = create_holding_detail_tool(ghostfolio_client, fmp=fmp)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" in result
        assert "Implied Downside" in result
        assert "-13.0%" in result

    @pytest.mark.asyncio
    async def test_smart_summary_absent_without_enrichment(self, ghostfolio_client):
        """No 3rd party clients → no 'Smart Summary' section."""
        tool = create_holding_detail_tool(ghostfolio_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" not in result

    @pytest.mark.asyncio
    async def test_smart_summary_partial_data(self, ghostfolio_client, fmp_client):
        """Only FMP provided → has implied upside but no analyst signal or earnings alert."""
        tool = create_holding_detail_tool(ghostfolio_client, fmp=fmp_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" in result
        assert "Implied Upside" in result
        # No Finnhub data → no analyst signal
        assert "Analyst Signal" not in result
        # No Finnhub earnings → no earnings alert
        assert "Earnings Alert" not in result

    @pytest.mark.asyncio
    async def test_conviction_score_in_smart_summary(
        self, ghostfolio_client, finnhub_client, alpha_vantage_client, fmp_client
    ):
        """Full enrichment → Smart Summary includes Conviction Score line."""
        tool = create_holding_detail_tool(
            ghostfolio_client,
            finnhub=finnhub_client,
            alpha_vantage=alpha_vantage_client,
            fmp=fmp_client,
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Smart Summary" in result
        assert "Conviction Score:" in result
        assert "/100" in result

    @pytest.mark.asyncio
    async def test_conviction_score_absent_without_enrichment(self, ghostfolio_client):
        """No 3rd party clients → no Conviction Score line."""
        tool = create_holding_detail_tool(ghostfolio_client)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Conviction Score:" not in result
