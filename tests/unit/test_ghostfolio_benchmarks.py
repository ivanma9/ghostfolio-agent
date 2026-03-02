"""Unit tests for GhostfolioClient.get_benchmarks and get_benchmark_detail."""

import pytest
import respx
import httpx

from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.exceptions import TransientError, AuthenticationError

BASE_URL = "http://localhost:3333"


@pytest.fixture
def client():
    return GhostfolioClient(base_url=BASE_URL, access_token="test-token")


class TestGetBenchmarks:
    @respx.mock
    async def test_get_benchmarks_returns_list(self, client):
        respx.get(f"{BASE_URL}/api/v1/benchmarks").mock(
            return_value=httpx.Response(
                200,
                json={
                    "benchmarks": [
                        {
                            "dataSource": "YAHOO",
                            "symbol": "SPY",
                            "name": "S&P 500",
                            "marketCondition": "NEUTRAL_MARKET",
                            "performances": {
                                "allTimeHigh": {
                                    "date": "2025-02-19T00:00:00.000Z",
                                    "performancePercent": -0.05,
                                }
                            },
                            "trend50d": "UP",
                            "trend200d": "UP",
                        },
                        {
                            "dataSource": "YAHOO",
                            "symbol": "QQQ",
                            "name": "NASDAQ 100",
                            "marketCondition": "ALL_TIME_HIGH",
                            "performances": {
                                "allTimeHigh": {
                                    "date": "2025-03-01T00:00:00.000Z",
                                    "performancePercent": 0.0,
                                }
                            },
                            "trend50d": "UP",
                            "trend200d": "UP",
                        },
                    ]
                },
            )
        )
        result = await client.get_benchmarks()
        assert "benchmarks" in result
        benchmarks = result["benchmarks"]
        assert len(benchmarks) == 2
        assert benchmarks[0]["symbol"] == "SPY"
        assert benchmarks[1]["symbol"] == "QQQ"
        assert benchmarks[0]["marketCondition"] == "NEUTRAL_MARKET"

    @respx.mock
    async def test_get_benchmarks_empty(self, client):
        respx.get(f"{BASE_URL}/api/v1/benchmarks").mock(
            return_value=httpx.Response(200, json={"benchmarks": []})
        )
        result = await client.get_benchmarks()
        assert "benchmarks" in result
        assert result["benchmarks"] == []

    @respx.mock
    async def test_get_benchmarks_api_error(self, client):
        respx.get(f"{BASE_URL}/api/v1/benchmarks").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(TransientError):
            await client.get_benchmarks()


class TestGetBenchmarkDetail:
    @respx.mock
    async def test_get_benchmark_detail_returns_market_data(self, client):
        respx.get(
            f"{BASE_URL}/api/v1/benchmarks/YAHOO/SPY/2020-01-01",
            params={"range": "max"},
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "marketData": [
                        {"date": "2020-01-01", "value": 0.0},
                        {"date": "2020-06-01", "value": 12.5},
                        {"date": "2021-01-01", "value": 28.3},
                    ]
                },
            )
        )
        result = await client.get_benchmark_detail("YAHOO", "SPY", "2020-01-01")
        assert "marketData" in result
        market_data = result["marketData"]
        assert len(market_data) == 3
        assert market_data[0]["date"] == "2020-01-01"
        assert market_data[0]["value"] == 0.0
        assert market_data[2]["value"] == 28.3

    @respx.mock
    async def test_get_benchmark_detail_default_range(self, client):
        """Verify that "max" is the default range when none is specified."""
        respx.get(
            f"{BASE_URL}/api/v1/benchmarks/YAHOO/SPY/2020-01-01",
            params={"range": "max"},
        ).mock(
            return_value=httpx.Response(
                200,
                json={"marketData": [{"date": "2020-01-01", "value": 0.0}]},
            )
        )
        # Call without explicit date_range — should default to "max"
        result = await client.get_benchmark_detail("YAHOO", "SPY", "2020-01-01")
        assert result["marketData"][0]["date"] == "2020-01-01"

    @respx.mock
    async def test_get_benchmark_detail_custom_range(self, client):
        """Verify that a custom range param is passed through correctly."""
        respx.get(
            f"{BASE_URL}/api/v1/benchmarks/YAHOO/QQQ/2023-01-01",
            params={"range": "1y"},
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "marketData": [
                        {"date": "2023-01-01", "value": 0.0},
                        {"date": "2024-01-01", "value": 35.7},
                    ]
                },
            )
        )
        result = await client.get_benchmark_detail(
            "YAHOO", "QQQ", "2023-01-01", date_range="1y"
        )
        assert len(result["marketData"]) == 2
        assert result["marketData"][1]["value"] == 35.7

    @respx.mock
    async def test_get_benchmark_detail_auth_error(self, client):
        respx.get(
            f"{BASE_URL}/api/v1/benchmarks/YAHOO/SPY/2020-01-01",
            params={"range": "max"},
        ).mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(AuthenticationError):
            await client.get_benchmark_detail("YAHOO", "SPY", "2020-01-01")
