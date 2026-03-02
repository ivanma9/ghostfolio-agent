"""Tests for GET /api/paper-portfolio endpoint."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from ghostfolio_agent.api.chat import get_paper_portfolio
from ghostfolio_agent.tools.paper_trade import _STARTING_CASH

# Default user for tests (auth disabled mode)
_DEFAULT_USER = {"id": "default", "role": "admin"}


@pytest.fixture(autouse=True)
def mock_client():
    """Mock the GhostfolioClient used by the endpoint for price lookups."""
    mock = AsyncMock()
    with patch("ghostfolio_agent.api.chat._get_client", return_value=mock):
        yield mock


@pytest.fixture(autouse=True)
def mock_user_client(mock_client):
    """Mock _get_user_client to return the same mock client."""
    async def _side_effect(user):
        return mock_client
    with patch("ghostfolio_agent.api.chat._get_user_client", side_effect=_side_effect):
        yield


class TestPaperPortfolioEndpoint:
    async def test_empty_portfolio(self, mock_client):
        """Empty portfolio returns cash=$100K, no positions."""
        mock_db = AsyncMock()
        mock_db.get_paper_portfolio = AsyncMock(return_value={
            "cash": _STARTING_CASH,
            "positions": {},
            "trades": [],
        })
        with patch("ghostfolio_agent.api.chat._get_auth_db", return_value=mock_db):
            result = await get_paper_portfolio(user=_DEFAULT_USER)

        assert result.cash == _STARTING_CASH
        assert result.total_value == _STARTING_CASH
        assert result.total_pnl == 0.0
        assert result.total_pnl_percent == 0.0
        assert result.positions == []

    async def test_portfolio_with_positions(self, mock_client):
        """Portfolio with positions returns correct values, allocations, P&L."""
        mock_client.lookup_symbol = AsyncMock(side_effect=[
            {"items": [{"dataSource": "YAHOO", "symbol": "AAPL"}]},
            {"items": [{"dataSource": "YAHOO", "symbol": "MSFT"}]},
        ])
        mock_client.get_symbol = AsyncMock(side_effect=[
            {"marketPrice": 200.0},  # AAPL current price
            {"marketPrice": 400.0},  # MSFT current price
        ])

        mock_db = AsyncMock()
        mock_db.get_paper_portfolio = AsyncMock(return_value={
            "cash": 80000.0,
            "positions": {
                "AAPL": {"quantity": 50, "avg_cost": 150.0},
                "MSFT": {"quantity": 25, "avg_cost": 350.0},
            },
            "trades": [],
        })
        with patch("ghostfolio_agent.api.chat._get_auth_db", return_value=mock_db):
            result = await get_paper_portfolio(user=_DEFAULT_USER)

        assert result.cash == 80000.0
        # AAPL: 50 * 200 = 10000, MSFT: 25 * 400 = 10000
        assert result.total_value == 100000.0  # 80k + 10k + 10k
        assert result.total_pnl == 0.0  # 100k - 100k starting
        assert result.total_pnl_percent == 0.0

        assert len(result.positions) == 2

        aapl = next(p for p in result.positions if p.symbol == "AAPL")
        assert aapl.quantity == 50
        assert aapl.avg_cost == 150.0
        assert aapl.current_price == 200.0
        assert aapl.value == 10000.0
        assert aapl.pnl == 2500.0  # (200-150)*50
        assert abs(aapl.pnl_percent - 33.33) < 0.1
        assert aapl.allocation == 10.0  # 10k/100k * 100

        msft = next(p for p in result.positions if p.symbol == "MSFT")
        assert msft.quantity == 25
        assert msft.avg_cost == 350.0
        assert msft.current_price == 400.0
        assert msft.value == 10000.0
        assert msft.pnl == 1250.0  # (400-350)*25
        assert abs(msft.pnl_percent - 14.29) < 0.1
        assert msft.allocation == 10.0

    async def test_price_lookup_failure_uses_avg_cost(self, mock_client):
        """When live price lookup fails, falls back to avg_cost."""
        mock_client.lookup_symbol = AsyncMock(side_effect=Exception("API error"))

        mock_db = AsyncMock()
        mock_db.get_paper_portfolio = AsyncMock(return_value={
            "cash": 90000.0,
            "positions": {
                "AAPL": {"quantity": 10, "avg_cost": 150.0},
            },
            "trades": [],
        })
        with patch("ghostfolio_agent.api.chat._get_auth_db", return_value=mock_db):
            result = await get_paper_portfolio(user=_DEFAULT_USER)

        assert len(result.positions) == 1
        assert result.positions[0].current_price == 150.0  # fallback to avg_cost
        assert result.positions[0].pnl == 0.0  # no change
        assert result.total_value == 91500.0  # 90k + 10*150
