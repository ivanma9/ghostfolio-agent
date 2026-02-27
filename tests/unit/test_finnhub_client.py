import pytest
import respx
import httpx
from ghostfolio_agent.clients.finnhub import FinnhubClient


@pytest.fixture
def client():
    return FinnhubClient(api_key="test-key")


class TestCongressionalTrading:
    @respx.mock
    async def test_returns_congressional_trades(self, client):
        respx.get(
            "https://finnhub.io/api/v1/stock/congressional-trading",
            params={"symbol": "NVDA", "token": "test-key"},
        ).mock(return_value=httpx.Response(200, json={
            "symbol": "NVDA",
            "data": [
                {
                    "transactionDate": "2026-01-15",
                    "transactionType": "Purchase",
                    "name": "Nancy Pelosi",
                    "amountFrom": 500000,
                    "amountTo": 1000000,
                    "assetName": "NVIDIA Corp",
                    "ownerType": "joint",
                    "position": "Representative",
                    "filingDate": "2026-01-30",
                }
            ],
        }))
        result = await client.get_congressional_trading("NVDA")
        assert len(result) == 1
        assert result[0]["name"] == "Nancy Pelosi"
        assert result[0]["transactionType"] == "Purchase"

    @respx.mock
    async def test_returns_empty_list_on_no_data(self, client):
        respx.get(
            "https://finnhub.io/api/v1/stock/congressional-trading",
            params={"symbol": "UNKNOWN", "token": "test-key"},
        ).mock(return_value=httpx.Response(200, json={"symbol": "UNKNOWN", "data": []}))
        result = await client.get_congressional_trading("UNKNOWN")
        assert result == []

    @respx.mock
    async def test_raises_on_api_error(self, client):
        respx.get(
            "https://finnhub.io/api/v1/stock/congressional-trading",
            params={"symbol": "NVDA", "token": "test-key"},
        ).mock(return_value=httpx.Response(401, text="Unauthorized"))
        with pytest.raises(RuntimeError, match="Finnhub API error"):
            await client.get_congressional_trading("NVDA")


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
