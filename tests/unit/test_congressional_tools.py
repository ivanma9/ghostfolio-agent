"""Tests for congressional trading tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ghostfolio_agent.tools.congressional import (
    create_congressional_trades_tool,
    create_congressional_summary_tool,
    create_congressional_members_tool,
)


TRADES_RESPONSE = {
    "trades": [
        {
            "member": "Nancy Pelosi",
            "ticker": "AAPL",
            "transaction_type": "purchase",
            "amount": "$100,001 - $250,000",
            "date": "2026-02-20",
        },
        {
            "member": "Dan Crenshaw",
            "ticker": "AAPL",
            "transaction_type": "sale",
            "amount": "$15,001 - $50,000",
            "date": "2026-02-18",
        },
    ],
    "total": 2,
}

SUMMARY_RESPONSE = {
    "ticker": "AAPL",
    "total_trades": 5,
    "buys": 3,
    "sells": 2,
    "unique_members": 4,
    "sentiment": "Bullish",
}

MEMBERS_RESPONSE = [
    {"member": "Nancy Pelosi", "trade_count": 42},
    {"member": "Dan Crenshaw", "trade_count": 15},
]


@pytest.fixture
def congressional_client():
    client = MagicMock()
    client.get_trades = AsyncMock(return_value=TRADES_RESPONSE)
    client.get_trades_summary = AsyncMock(return_value=SUMMARY_RESPONSE)
    client.get_members = AsyncMock(return_value=MEMBERS_RESPONSE)
    return client


class TestCongressionalTradesTool:
    @pytest.mark.asyncio
    async def test_returns_trades(self, congressional_client):
        tool = create_congressional_trades_tool(congressional_client)
        result = await tool.ainvoke({"ticker": "AAPL"})
        assert "Nancy Pelosi" in result
        assert "AAPL" in result
        assert "purchase" in result
        assert "DATA_SOURCES" in result

    @pytest.mark.asyncio
    async def test_empty_trades(self, congressional_client):
        congressional_client.get_trades = AsyncMock(return_value={"trades": [], "total": 0})
        tool = create_congressional_trades_tool(congressional_client)
        result = await tool.ainvoke({"ticker": "ZZZZ"})
        assert "No congressional trades" in result

    @pytest.mark.asyncio
    async def test_api_error_graceful(self, congressional_client):
        congressional_client.get_trades = AsyncMock(side_effect=RuntimeError("down"))
        tool = create_congressional_trades_tool(congressional_client)
        result = await tool.ainvoke({"ticker": "AAPL"})
        assert "unavailable" in result.lower()
        assert "down" not in result.lower()


class TestCongressionalSummaryTool:
    @pytest.mark.asyncio
    async def test_returns_summary(self, congressional_client):
        tool = create_congressional_summary_tool(congressional_client)
        result = await tool.ainvoke({"ticker": "AAPL"})
        assert "5" in result  # total trades
        assert "Buys" in result
        assert "Sells" in result
        assert "Bullish" in result
        assert "DATA_SOURCES" in result

    @pytest.mark.asyncio
    async def test_empty_summary(self, congressional_client):
        congressional_client.get_trades_summary = AsyncMock(return_value={"total_trades": 0})
        tool = create_congressional_summary_tool(congressional_client)
        result = await tool.ainvoke({"ticker": "ZZZZ"})
        assert "No congressional trades" in result

    @pytest.mark.asyncio
    async def test_api_error_graceful(self, congressional_client):
        congressional_client.get_trades_summary = AsyncMock(side_effect=RuntimeError("down"))
        tool = create_congressional_summary_tool(congressional_client)
        result = await tool.ainvoke({"ticker": "AAPL"})
        assert "unavailable" in result.lower()


class TestCongressionalMembersTool:
    @pytest.mark.asyncio
    async def test_returns_members(self, congressional_client):
        tool = create_congressional_members_tool(congressional_client)
        result = await tool.ainvoke({})
        assert "Nancy Pelosi" in result
        assert "42 trades" in result
        assert "DATA_SOURCES" in result

    @pytest.mark.asyncio
    async def test_empty_members(self, congressional_client):
        congressional_client.get_members = AsyncMock(return_value=[])
        tool = create_congressional_members_tool(congressional_client)
        result = await tool.ainvoke({})
        assert "No congressional member" in result

    @pytest.mark.asyncio
    async def test_api_error_graceful(self, congressional_client):
        congressional_client.get_members = AsyncMock(side_effect=RuntimeError("down"))
        tool = create_congressional_members_tool(congressional_client)
        result = await tool.ainvoke({})
        assert "unavailable" in result.lower()


class TestPartialData:
    """Verify tools handle partial/missing fields gracefully via .get() defaults."""

    @pytest.fixture(autouse=True)
    def _client(self):
        self.client = MagicMock()

    @pytest.mark.asyncio
    async def test_trades_missing_fields_in_entry(self):
        """Trade with only 'member' key — other fields use .get() defaults."""
        self.client.get_trades = AsyncMock(
            return_value={"trades": [{"member": "Pelosi"}], "total": 1}
        )
        tool = create_congressional_trades_tool(self.client)
        result = await tool.ainvoke({"ticker": "AAPL"})
        assert "Pelosi" in result
        assert "?" in result  # ticker default
        assert "N/A" in result  # amount default

    @pytest.mark.asyncio
    async def test_trades_none_values_in_entry(self):
        """All fields None — graceful formatting."""
        self.client.get_trades = AsyncMock(
            return_value={
                "trades": [{"member": None, "ticker": None, "transaction_type": None, "amount": None, "date": None}],
                "total": 1,
            }
        )
        tool = create_congressional_trades_tool(self.client)
        result = await tool.ainvoke({"ticker": "AAPL"})
        # Should not crash — None values replaced by .get() defaults
        assert "Congressional Trades" in result

    @pytest.mark.asyncio
    async def test_summary_missing_sentiment(self):
        """No sentiment key — verify 'N/A' default."""
        self.client.get_trades_summary = AsyncMock(
            return_value={"total_trades": 3, "buys": 2, "sells": 1, "unique_members": 2}
        )
        tool = create_congressional_summary_tool(self.client)
        result = await tool.ainvoke({"ticker": "AAPL"})
        assert "N/A" in result

    @pytest.mark.asyncio
    async def test_summary_missing_buys_sells_keys(self):
        """No buys/sells keys — verify defaults to 0."""
        self.client.get_trades_summary = AsyncMock(
            return_value={"total_trades": 5, "unique_members": 3, "sentiment": "Neutral"}
        )
        tool = create_congressional_summary_tool(self.client)
        result = await tool.ainvoke({"ticker": "AAPL"})
        assert "Buys:" in result
        assert "Sells:" in result

    @pytest.mark.asyncio
    async def test_members_entry_missing_trade_count(self):
        """Member missing trade_count — defaults to 0."""
        self.client.get_members = AsyncMock(
            return_value=[{"member": "Pelosi"}]
        )
        tool = create_congressional_members_tool(self.client)
        result = await tool.ainvoke({})
        assert "Pelosi" in result
        assert "0 trades" in result

    @pytest.mark.asyncio
    async def test_members_entry_null_name(self):
        """Member name is None — defaults to 'Unknown'."""
        self.client.get_members = AsyncMock(
            return_value=[{"member": None, "trade_count": 5}]
        )
        tool = create_congressional_members_tool(self.client)
        result = await tool.ainvoke({})
        assert "Unknown" in result
        assert "5 trades" in result
