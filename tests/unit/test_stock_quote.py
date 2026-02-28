import pytest
import respx
import httpx
from unittest.mock import AsyncMock, patch
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.tools.stock_quote import create_stock_quote_tool


@pytest.fixture
def finnhub():
    return FinnhubClient(api_key="test-key")


@pytest.fixture
def ghostfolio():
    client = AsyncMock(spec=GhostfolioClient)
    client.lookup_symbol = AsyncMock(return_value={
        "items": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "currency": "USD",
                "assetSubClass": "STOCK",
                "dataSource": "YAHOO",
            }
        ]
    })
    client.get_symbol = AsyncMock(return_value={"marketPrice": 185.50})
    return client


class TestFinnhubGetQuote:
    @respx.mock
    async def test_returns_quote(self, finnhub):
        respx.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": "AAPL", "token": "test-key"},
        ).mock(return_value=httpx.Response(200, json={
            "c": 185.92,
            "d": 2.42,
            "dp": 1.318,
            "h": 186.50,
            "l": 183.10,
            "o": 184.00,
            "pc": 183.50,
            "t": 1700000000,
        }))
        result = await finnhub.get_quote("AAPL")
        assert result["c"] == 185.92
        assert result["dp"] == 1.318

    @respx.mock
    async def test_raises_on_api_error(self, finnhub):
        respx.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": "AAPL", "token": "test-key"},
        ).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        with pytest.raises(RuntimeError, match="Finnhub API error"):
            await finnhub.get_quote("AAPL")


class TestStockQuoteTool:
    async def test_full_quote_with_finnhub(self, ghostfolio):
        finnhub = AsyncMock(spec=FinnhubClient)
        finnhub.get_quote = AsyncMock(return_value={
            "c": 185.92, "d": 2.42, "dp": 1.32,
            "h": 186.50, "l": 183.10, "o": 184.00, "pc": 183.50,
        })
        tool = create_stock_quote_tool(ghostfolio, finnhub=finnhub)
        result = await tool.ainvoke({"symbol": "AAPL"})
        assert "AAPL" in result
        assert "185.92" in result
        assert "+2.42" in result
        assert "186.50" in result
        assert "183.10" in result

    async def test_fallback_to_ghostfolio_when_no_finnhub(self, ghostfolio):
        tool = create_stock_quote_tool(ghostfolio, finnhub=None)
        result = await tool.ainvoke({"symbol": "AAPL"})
        assert "AAPL" in result
        assert "185.50" in result

    async def test_fallback_when_finnhub_errors(self, ghostfolio):
        finnhub = AsyncMock(spec=FinnhubClient)
        finnhub.get_quote = AsyncMock(side_effect=Exception("timeout"))
        tool = create_stock_quote_tool(ghostfolio, finnhub=finnhub)
        result = await tool.ainvoke({"symbol": "AAPL"})
        assert "AAPL" in result
        assert "185.50" in result

    async def test_symbol_not_found(self, ghostfolio):
        ghostfolio.lookup_symbol = AsyncMock(return_value={"items": []})
        tool = create_stock_quote_tool(ghostfolio, finnhub=None)
        result = await tool.ainvoke({"symbol": "ZZZZZZ"})
        assert "not found" in result.lower()

    async def test_fallback_when_finnhub_returns_zero_price(self, ghostfolio):
        finnhub = AsyncMock(spec=FinnhubClient)
        finnhub.get_quote = AsyncMock(return_value={
            "c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0,
        })
        tool = create_stock_quote_tool(ghostfolio, finnhub=finnhub)
        result = await tool.ainvoke({"symbol": "AAPL"})
        # Should fall through to Ghostfolio price
        assert "185.50" in result

    async def test_prefers_usd_stock(self, ghostfolio):
        ghostfolio.lookup_symbol = AsyncMock(return_value={
            "items": [
                {"symbol": "AAPL.DE", "name": "Apple (Frankfurt)", "currency": "EUR", "assetSubClass": "STOCK", "dataSource": "YAHOO"},
                {"symbol": "AAPL", "name": "Apple Inc.", "currency": "USD", "assetSubClass": "STOCK", "dataSource": "YAHOO"},
            ]
        })
        tool = create_stock_quote_tool(ghostfolio, finnhub=None)
        result = await tool.ainvoke({"symbol": "AAPL"})
        assert "AAPL" in result
        # Should resolve to AAPL (USD), not AAPL.DE
        ghostfolio.get_symbol.assert_called_with("YAHOO", "AAPL")
