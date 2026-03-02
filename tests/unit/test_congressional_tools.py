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
