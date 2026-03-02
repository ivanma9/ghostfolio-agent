import pytest
from ghostfolio_agent.tools.conviction_score import compute_analyst_score


class TestAnalystScore:
    def test_all_strong_buy(self):
        """All strong buy → 100."""
        data = [{"strongBuy": 10, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}]
        score, explanation = compute_analyst_score(data)
        assert score == 100
        assert "10 of 10" in explanation

    def test_all_strong_sell(self):
        """All strong sell → 0."""
        data = [{"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 10}]
        score, explanation = compute_analyst_score(data)
        assert score == 0

    def test_mixed(self):
        """12 strongBuy + 18 buy + 6 hold + 1 sell → high score."""
        data = [{"strongBuy": 12, "buy": 18, "hold": 6, "sell": 1, "strongSell": 0}]
        score, explanation = compute_analyst_score(data)
        assert 70 <= score <= 90
        assert "30 of 37" in explanation

    def test_all_hold(self):
        """All hold → 50."""
        data = [{"strongBuy": 0, "buy": 0, "hold": 10, "sell": 0, "strongSell": 0}]
        score, explanation = compute_analyst_score(data)
        assert score == 50

    def test_none_data(self):
        """None input → None."""
        score, explanation = compute_analyst_score(None)
        assert score is None
        assert explanation == "No analyst data"

    def test_empty_list(self):
        """Empty list → None."""
        score, explanation = compute_analyst_score([])
        assert score is None


from ghostfolio_agent.tools.conviction_score import compute_price_target_score


class TestPriceTargetScore:
    def test_large_upside(self):
        """+30% upside or more → 100."""
        data = [{"targetConsensus": 260.0}]
        score, explanation = compute_price_target_score(data, 200.0)
        assert score == 100
        assert "+30.0%" in explanation

    def test_large_downside(self):
        """-30% or worse → 0."""
        data = [{"targetConsensus": 140.0}]
        score, explanation = compute_price_target_score(data, 200.0)
        assert score == 0

    def test_no_change(self):
        """Target equals market → 50."""
        data = [{"targetConsensus": 200.0}]
        score, explanation = compute_price_target_score(data, 200.0)
        assert score == 50

    def test_moderate_upside(self):
        """+15% upside → 75."""
        data = [{"targetConsensus": 230.0}]
        score, explanation = compute_price_target_score(data, 200.0)
        assert score == 75
        assert "+15.0%" in explanation

    def test_none_data(self):
        """None input → None."""
        score, explanation = compute_price_target_score(None, 200.0)
        assert score is None

    def test_zero_market_price(self):
        """Zero market price → None (avoid division by zero)."""
        data = [{"targetConsensus": 200.0}]
        score, explanation = compute_price_target_score(data, 0.0)
        assert score is None


from datetime import date, timedelta
from ghostfolio_agent.tools.conviction_score import (
    compute_sentiment_score,
    compute_earnings_score,
)


class TestSentimentScore:
    def test_all_bullish(self):
        """All bullish articles → 100."""
        news = [
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Somewhat-Bullish"},
        ]
        score, explanation = compute_sentiment_score(news)
        assert score == 100
        assert "2 of 2" in explanation

    def test_all_bearish(self):
        """All bearish articles → 0."""
        news = [
            {"overall_sentiment_label": "Bearish"},
            {"overall_sentiment_label": "Somewhat-Bearish"},
        ]
        score, explanation = compute_sentiment_score(news)
        assert score == 0

    def test_mixed(self):
        """3 bullish, 1 neutral, 1 bearish → 70. (3*1 + 1*0.5 + 1*0) / 5 = 0.7."""
        news = [
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Somewhat-Bullish"},
            {"overall_sentiment_label": "Bullish"},
            {"overall_sentiment_label": "Neutral"},
            {"overall_sentiment_label": "Bearish"},
        ]
        score, explanation = compute_sentiment_score(news)
        assert score == 70
        assert "3 of 5" in explanation

    def test_all_neutral(self):
        """All neutral → 50."""
        news = [{"overall_sentiment_label": "Neutral"}] * 4
        score, explanation = compute_sentiment_score(news)
        assert score == 50

    def test_none_data(self):
        """None → None."""
        score, explanation = compute_sentiment_score(None)
        assert score is None

    def test_empty_list(self):
        """Empty → None."""
        score, explanation = compute_sentiment_score([])
        assert score is None


class TestEarningsScore:
    def test_no_upcoming(self):
        """No earnings data → 75 (stable)."""
        score, explanation = compute_earnings_score(None)
        assert score == 75
        assert "No upcoming" in explanation

    def test_earnings_within_14_days(self):
        """Earnings in 8 days → 50 (uncertainty)."""
        earn_date = (date.today() + timedelta(days=8)).isoformat()
        data = [{"date": earn_date}]
        score, explanation = compute_earnings_score(data)
        assert score == 50
        assert "8 days" in explanation

    def test_earnings_far_away(self):
        """Earnings 45 days away → 75 (stable, same as no upcoming)."""
        earn_date = (date.today() + timedelta(days=45)).isoformat()
        data = [{"date": earn_date}]
        score, explanation = compute_earnings_score(data)
        assert score == 75

    def test_earnings_today(self):
        """Earnings today → 50."""
        earn_date = date.today().isoformat()
        data = [{"date": earn_date}]
        score, explanation = compute_earnings_score(data)
        assert score == 50
        assert "0 days" in explanation

    def test_empty_list(self):
        """Empty list → 75 (stable)."""
        score, explanation = compute_earnings_score([])
        assert score == 75


from ghostfolio_agent.tools.conviction_score import compute_congressional_score


class TestCongressionalScore:
    def test_all_buys(self):
        """All buys → 100."""
        data = {"total_trades": 5, "buys": 5, "sells": 0, "unique_members": 3}
        score, explanation = compute_congressional_score(data)
        assert score == 100
        assert "5 buys" in explanation

    def test_all_sells(self):
        """All sells → 0."""
        data = {"total_trades": 4, "buys": 0, "sells": 4, "unique_members": 2}
        score, explanation = compute_congressional_score(data)
        assert score == 0
        assert "4 sells" in explanation

    def test_balanced(self):
        """Equal buys/sells → 50."""
        data = {"total_trades": 6, "buys": 3, "sells": 3, "unique_members": 4}
        score, explanation = compute_congressional_score(data)
        assert score == 50

    def test_too_few_trades(self):
        """< 2 trades → None."""
        data = {"total_trades": 1, "buys": 1, "sells": 0, "unique_members": 1}
        score, explanation = compute_congressional_score(data)
        assert score is None
        assert "Too few" in explanation

    def test_none_data(self):
        """None → None."""
        score, explanation = compute_congressional_score(None)
        assert score is None
        assert "No congressional data" in explanation


from ghostfolio_agent.tools.conviction_score import compute_composite, score_to_label


class TestComposite:
    def test_all_components(self):
        """All 5 components present — weighted average."""
        components = [
            ("analyst", 80, "18 of 24 bullish", 35),
            ("price_target", 70, "+12% upside", 25),
            ("sentiment", 60, "3 of 5 positive", 15),
            ("congressional", 75, "3 buys, 1 sell", 15),
            ("earnings", 50, "Reporting in 8 days", 10),
        ]
        score, label, details = compute_composite(components)
        # (80*35 + 70*25 + 60*15 + 75*15 + 50*10) / 100 = (2800+1750+900+1125+500)/100 = 70.75 → 71
        assert 70 <= score <= 72
        assert label == "Buy"
        assert len(details) == 5

    def test_missing_one_component(self):
        """4 components — weights redistribute."""
        components = [
            ("analyst", 80, "18 of 24 bullish", 35),
            ("price_target", 70, "+12% upside", 25),
            ("congressional", 75, "3 buys, 1 sell", 15),
            ("earnings", 50, "Reporting in 8 days", 10),
        ]
        score, label, details = compute_composite(components)
        # Total weight = 85
        assert 70 <= score <= 76
        assert label == "Buy"

    def test_single_component(self):
        """Only one component — uses its score directly."""
        components = [
            ("analyst", 85, "20 of 24 bullish", 35),
        ]
        score, label, details = compute_composite(components)
        assert score == 85
        assert label == "Strong Buy"

    def test_empty_components(self):
        """No components → None."""
        score, label, details = compute_composite([])
        assert score is None
        assert label == "Insufficient Data"


class TestScoreToLabel:
    def test_strong_sell(self):
        assert score_to_label(10) == "Strong Sell"
        assert score_to_label(0) == "Strong Sell"
        assert score_to_label(20) == "Strong Sell"

    def test_sell(self):
        assert score_to_label(21) == "Sell"
        assert score_to_label(40) == "Sell"

    def test_neutral(self):
        assert score_to_label(41) == "Neutral"
        assert score_to_label(60) == "Neutral"

    def test_buy(self):
        assert score_to_label(61) == "Buy"
        assert score_to_label(80) == "Buy"

    def test_strong_buy(self):
        assert score_to_label(81) == "Strong Buy"
        assert score_to_label(100) == "Strong Buy"


from unittest.mock import AsyncMock, MagicMock
from ghostfolio_agent.tools.conviction_score import create_conviction_score_tool


ANALYST_MOCK = [
    {"period": "2026-03-01", "strongBuy": 12, "buy": 18, "hold": 6, "sell": 1, "strongSell": 0}
]

NEWS_MOCK = [
    {"title": "Apple beats earnings", "overall_sentiment_label": "Bullish", "source": "Reuters"},
    {"title": "Tech rally continues", "overall_sentiment_label": "Somewhat-Bullish", "source": "CNBC"},
    {"title": "Market concerns", "overall_sentiment_label": "Bearish", "source": "WSJ"},
]

PT_CONSENSUS_MOCK = [
    {"symbol": "AAPL", "targetConsensus": 220.50}
]

QUOTE_MOCK = {"c": 195.50, "h": 198.0, "l": 193.0, "o": 194.0, "pc": 193.50}


class TestConvictionScoreTool:
    @pytest.mark.asyncio
    async def test_full_score_output(self):
        """All clients configured — returns score with all 4 components."""
        finnhub = MagicMock()
        finnhub.get_analyst_recommendations = AsyncMock(return_value=ANALYST_MOCK)
        finnhub.get_earnings_calendar = AsyncMock(return_value=[])
        finnhub.get_quote = AsyncMock(return_value=QUOTE_MOCK)

        alpha_vantage = MagicMock()
        alpha_vantage.get_news_sentiment = AsyncMock(return_value=NEWS_MOCK)

        fmp = MagicMock()
        fmp.get_price_target_consensus = AsyncMock(return_value=PT_CONSENSUS_MOCK)

        tool = create_conviction_score_tool(
            finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Conviction Score" in result
        assert "/100" in result
        assert "Analyst Consensus" in result
        assert "Price Target Upside" in result
        assert "News Sentiment" in result
        assert "Earnings Proximity" in result

    @pytest.mark.asyncio
    async def test_missing_alpha_vantage(self):
        """No Alpha Vantage — 3 components, sentiment shows N/A."""
        finnhub = MagicMock()
        finnhub.get_analyst_recommendations = AsyncMock(return_value=ANALYST_MOCK)
        finnhub.get_earnings_calendar = AsyncMock(return_value=[])
        finnhub.get_quote = AsyncMock(return_value=QUOTE_MOCK)

        fmp = MagicMock()
        fmp.get_price_target_consensus = AsyncMock(return_value=PT_CONSENSUS_MOCK)

        tool = create_conviction_score_tool(finnhub=finnhub, fmp=fmp)
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "Conviction Score" in result
        assert "/100" in result
        assert "N/A" in result

    @pytest.mark.asyncio
    async def test_no_clients(self):
        """No clients configured — error message."""
        tool = create_conviction_score_tool()
        result = await tool.ainvoke({"symbol": "AAPL"})

        assert "not available" in result.lower() or "no data sources" in result.lower()

    @pytest.mark.asyncio
    async def test_api_errors_graceful(self):
        """All APIs error — graceful degradation."""
        finnhub = MagicMock()
        finnhub.get_analyst_recommendations = AsyncMock(side_effect=RuntimeError("down"))
        finnhub.get_earnings_calendar = AsyncMock(side_effect=RuntimeError("down"))
        finnhub.get_quote = AsyncMock(side_effect=RuntimeError("down"))

        alpha_vantage = MagicMock()
        alpha_vantage.get_news_sentiment = AsyncMock(side_effect=RuntimeError("down"))

        fmp = MagicMock()
        fmp.get_price_target_consensus = AsyncMock(side_effect=RuntimeError("down"))

        tool = create_conviction_score_tool(
            finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp
        )
        result = await tool.ainvoke({"symbol": "AAPL"})

        # Should not crash, should indicate insufficient data or show partial results
        assert "down" not in result.lower()
