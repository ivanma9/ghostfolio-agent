import pytest
import respx
import httpx
from ghostfolio_agent.clients.fmp import FMPClient
from ghostfolio_agent.clients.exceptions import APIError, TransientError, AuthenticationError


@pytest.fixture
def client():
    return FMPClient(api_key="test-key")


class TestPriceTargetConsensus:
    @respx.mock
    async def test_returns_consensus(self, client):
        respx.get(
            "https://financialmodelingprep.com/stable/price-target-consensus",
            params={"symbol": "AAPL", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[
            {
                "symbol": "AAPL",
                "targetHigh": 250.0,
                "targetLow": 180.0,
                "targetConsensus": 220.5,
                "targetMedian": 225.0,
            }
        ]))
        result = await client.get_price_target_consensus("AAPL")
        assert len(result) == 1
        assert result[0]["targetConsensus"] == 220.5

    @respx.mock
    async def test_returns_empty_on_unknown_symbol(self, client):
        respx.get(
            "https://financialmodelingprep.com/stable/price-target-consensus",
            params={"symbol": "UNKNOWN", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[]))
        result = await client.get_price_target_consensus("UNKNOWN")
        assert result == []

    @respx.mock
    async def test_raises_on_api_error(self, client):
        respx.get(
            "https://financialmodelingprep.com/stable/price-target-consensus",
            params={"symbol": "AAPL", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(AuthenticationError):
            await client.get_price_target_consensus("AAPL")


class TestPriceTargetSummary:
    @respx.mock
    async def test_returns_summary(self, client):
        respx.get(
            "https://financialmodelingprep.com/stable/price-target-summary",
            params={"symbol": "TSLA", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[
            {
                "symbol": "TSLA",
                "lastMonthCount": 7,
                "lastMonthAvgPriceTarget": 454.0,
                "lastQuarterCount": 15,
                "lastQuarterAvgPriceTarget": 465.0,
                "allTimeCount": 247,
                "allTimeAvgPriceTarget": 301.64,
            }
        ]))
        result = await client.get_price_target_summary("TSLA")
        assert len(result) == 1
        assert result[0]["lastMonthCount"] == 7

    @respx.mock
    async def test_returns_empty_on_unknown_symbol(self, client):
        respx.get(
            "https://financialmodelingprep.com/stable/price-target-summary",
            params={"symbol": "UNKNOWN", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[]))
        result = await client.get_price_target_summary("UNKNOWN")
        assert result == []

    @respx.mock
    async def test_raises_on_api_error(self, client):
        respx.get(
            "https://financialmodelingprep.com/stable/price-target-summary",
            params={"symbol": "TSLA", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        with pytest.raises(TransientError):
            await client.get_price_target_summary("TSLA")
