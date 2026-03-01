import pytest
import respx
import httpx
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.exceptions import APIError, TransientError, AuthenticationError


@pytest.fixture
def client():
    return AlphaVantageClient(api_key="test-key")


class TestNewsSentiment:
    @respx.mock
    async def test_returns_sentiment_for_ticker(self, client):
        respx.get(
            "https://www.alphavantage.co/query",
            params={"function": "NEWS_SENTIMENT", "tickers": "AAPL", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json={
            "items": "10",
            "feed": [
                {
                    "title": "Apple Reports Strong Q1",
                    "url": "https://example.com/article",
                    "overall_sentiment_score": 0.25,
                    "overall_sentiment_label": "Somewhat_Bullish",
                    "ticker_sentiment": [
                        {
                            "ticker": "AAPL",
                            "relevance_score": "0.95",
                            "ticker_sentiment_score": "0.28",
                            "ticker_sentiment_label": "Somewhat_Bullish",
                        }
                    ],
                }
            ],
        }))
        result = await client.get_news_sentiment("AAPL")
        assert len(result) == 1
        assert result[0]["overall_sentiment_label"] == "Somewhat_Bullish"

    @respx.mock
    async def test_returns_empty_list_on_no_feed(self, client):
        respx.get(
            "https://www.alphavantage.co/query",
            params={"function": "NEWS_SENTIMENT", "tickers": "UNKNOWN", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json={"items": "0", "feed": []}))
        result = await client.get_news_sentiment("UNKNOWN")
        assert result == []

    @respx.mock
    async def test_raises_on_api_error(self, client):
        respx.get(
            "https://www.alphavantage.co/query",
            params={"function": "NEWS_SENTIMENT", "tickers": "AAPL", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        with pytest.raises(TransientError):
            await client.get_news_sentiment("AAPL")


class TestMacroIndicators:
    @respx.mock
    async def test_returns_fed_funds_rate(self, client):
        respx.get(
            "https://www.alphavantage.co/query",
            params={"function": "FEDERAL_FUNDS_RATE", "interval": "daily", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json={
            "name": "Federal Funds Effective Rate",
            "data": [{"date": "2026-02-26", "value": "4.33"}],
        }))
        result = await client.get_fed_funds_rate()
        assert result[0]["value"] == "4.33"

    @respx.mock
    async def test_returns_cpi(self, client):
        respx.get(
            "https://www.alphavantage.co/query",
            params={"function": "CPI", "interval": "monthly", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json={
            "name": "Consumer Price Index",
            "data": [{"date": "2026-01-01", "value": "315.2"}],
        }))
        result = await client.get_cpi()
        assert result[0]["value"] == "315.2"

    @respx.mock
    async def test_returns_treasury_yield(self, client):
        respx.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TREASURY_YIELD",
                "interval": "daily",
                "maturity": "10year",
                "apikey": "test-key",
            },
        ).mock(return_value=httpx.Response(200, json={
            "name": "10-Year Treasury Yield",
            "data": [{"date": "2026-02-26", "value": "4.52"}],
        }))
        result = await client.get_treasury_yield()
        assert result[0]["value"] == "4.52"

    @respx.mock
    async def test_raises_on_macro_api_error(self, client):
        respx.get(
            "https://www.alphavantage.co/query",
            params={"function": "FEDERAL_FUNDS_RATE", "interval": "daily", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(AuthenticationError):
            await client.get_fed_funds_rate()
