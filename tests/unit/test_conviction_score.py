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
