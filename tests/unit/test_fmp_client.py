import pytest
import respx
import httpx
from ghostfolio_agent.clients.fmp import FMPClient


@pytest.fixture
def client():
    return FMPClient(api_key="test-key")


class TestInsiderTrading:
    @respx.mock
    async def test_returns_insider_trades(self, client):
        respx.get(
            "https://financialmodelingprep.com/api/v4/insider-trading",
            params={"symbol": "AAPL", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[
            {
                "symbol": "AAPL",
                "filingDate": "2026-02-20",
                "transactionDate": "2026-02-18",
                "transactionType": "S-Sale",
                "securitiesOwned": 100000,
                "securitiesTransacted": 5000,
                "price": 185.50,
                "reportingName": "Tim Cook",
                "typeOfOwner": "officer",
            }
        ]))
        result = await client.get_insider_trading("AAPL")
        assert len(result) == 1
        assert result[0]["reportingName"] == "Tim Cook"
        assert result[0]["transactionType"] == "S-Sale"

    @respx.mock
    async def test_returns_empty_list_on_no_trades(self, client):
        respx.get(
            "https://financialmodelingprep.com/api/v4/insider-trading",
            params={"symbol": "UNKNOWN", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[]))
        result = await client.get_insider_trading("UNKNOWN")
        assert result == []

    @respx.mock
    async def test_raises_on_api_error(self, client):
        respx.get(
            "https://financialmodelingprep.com/api/v4/insider-trading",
            params={"symbol": "AAPL", "apikey": "test-key"},
        ).mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(RuntimeError, match="FMP API error"):
            await client.get_insider_trading("AAPL")


class TestAnalystEstimates:
    @respx.mock
    async def test_returns_analyst_estimates(self, client):
        respx.get(
            "https://financialmodelingprep.com/api/v3/analyst-estimates/TSLA",
            params={"apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[
            {
                "symbol": "TSLA",
                "date": "2026-03-31",
                "estimatedRevenueLow": 20000000000,
                "estimatedRevenueHigh": 28000000000,
                "estimatedRevenueAvg": 25000000000,
                "estimatedEpsLow": 0.55,
                "estimatedEpsHigh": 0.90,
                "estimatedEpsAvg": 0.72,
                "numberAnalystEstimatedRevenue": 30,
                "numberAnalystsEstimatedEps": 28,
            }
        ]))
        result = await client.get_analyst_estimates("TSLA")
        assert len(result) == 1
        assert result[0]["estimatedEpsAvg"] == 0.72

    @respx.mock
    async def test_returns_empty_list_when_no_estimates(self, client):
        respx.get(
            "https://financialmodelingprep.com/api/v3/analyst-estimates/UNKNOWN",
            params={"apikey": "test-key"},
        ).mock(return_value=httpx.Response(200, json=[]))
        result = await client.get_analyst_estimates("UNKNOWN")
        assert result == []

    @respx.mock
    async def test_raises_on_analyst_api_error(self, client):
        respx.get(
            "https://financialmodelingprep.com/api/v3/analyst-estimates/TSLA",
            params={"apikey": "test-key"},
        ).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        with pytest.raises(RuntimeError, match="FMP API error"):
            await client.get_analyst_estimates("TSLA")
