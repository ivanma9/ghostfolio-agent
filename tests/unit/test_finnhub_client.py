import pytest
import respx
import httpx
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.exceptions import APIError, TransientError


@pytest.fixture
def client():
    return FinnhubClient(api_key="test-key")


class TestAnalystRecommendations:
    @respx.mock
    async def test_returns_recommendations(self, client):
        respx.get(
            "https://finnhub.io/api/v1/stock/recommendation",
            params={"symbol": "AAPL", "token": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[
            {
                "symbol": "AAPL",
                "period": "2026-02-01",
                "strongBuy": 12,
                "buy": 20,
                "hold": 8,
                "sell": 2,
                "strongSell": 0,
            }
        ]))
        result = await client.get_analyst_recommendations("AAPL")
        assert len(result) == 1
        assert result[0]["strongBuy"] == 12

    @respx.mock
    async def test_returns_empty_list_when_no_recs(self, client):
        respx.get(
            "https://finnhub.io/api/v1/stock/recommendation",
            params={"symbol": "UNKNOWN", "token": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[]))
        result = await client.get_analyst_recommendations("UNKNOWN")
        assert result == []


class TestEarningsCalendar:
    @respx.mock
    async def test_returns_earnings(self, client):
        respx.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={"symbol": "TSLA", "token": "test-key"},
        ).mock(return_value=httpx.Response(200, json={
            "earningsCalendar": [
                {
                    "date": "2026-03-15",
                    "epsEstimate": 0.72,
                    "epsActual": None,
                    "hour": "amc",
                    "quarter": 1,
                    "revenueEstimate": 25000000000,
                    "revenueActual": None,
                    "symbol": "TSLA",
                    "year": 2026,
                }
            ]
        }))
        result = await client.get_earnings_calendar("TSLA")
        assert len(result) == 1
        assert result[0]["epsEstimate"] == 0.72
        assert result[0]["hour"] == "amc"

    @respx.mock
    async def test_raises_on_api_error(self, client):
        respx.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={"symbol": "TSLA", "token": "test-key"},
        ).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        with pytest.raises(TransientError):
            await client.get_earnings_calendar("TSLA")
