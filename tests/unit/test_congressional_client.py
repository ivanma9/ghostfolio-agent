"""Tests for CongressionalClient — happy paths, filters, error handling."""

import pytest
import httpx
import respx

from ghostfolio_agent.clients.congressional import CongressionalClient
from ghostfolio_agent.clients.exceptions import TransientError, APIError, RateLimitError

BASE_URL = "http://congressional-trading.railway.internal:8000"


@pytest.fixture
def client():
    return CongressionalClient(base_url=BASE_URL)


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

HEALTH_RESPONSE = {"status": "healthy", "last_scrape": "2026-02-28T10:00:00Z"}


class TestGetTrades:
    @respx.mock
    @pytest.mark.asyncio
    async def test_no_filters(self, client):
        respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(200, json=TRADES_RESPONSE)
        )
        result = await client.get_trades()
        assert result["total"] == 2
        assert len(result["trades"]) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_ticker_filter(self, client):
        route = respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(200, json=TRADES_RESPONSE)
        )
        await client.get_trades(ticker="AAPL")
        assert route.calls[0].request.url.params["ticker"] == "AAPL"

    @respx.mock
    @pytest.mark.asyncio
    async def test_member_filter(self, client):
        route = respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(200, json=TRADES_RESPONSE)
        )
        await client.get_trades(member="Nancy Pelosi")
        assert route.calls[0].request.url.params["member"] == "Nancy Pelosi"

    @respx.mock
    @pytest.mark.asyncio
    async def test_days_and_transaction_type_filters(self, client):
        route = respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(200, json=TRADES_RESPONSE)
        )
        await client.get_trades(days=30, transaction_type="purchase")
        params = route.calls[0].request.url.params
        assert params["days"] == "30"
        assert params["transaction_type"] == "purchase"

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_trades(self, client):
        respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(200, json={"trades": [], "total": 0})
        )
        result = await client.get_trades(ticker="ZZZZ")
        assert result["total"] == 0
        assert result["trades"] == []


class TestGetTradesSummary:
    @respx.mock
    @pytest.mark.asyncio
    async def test_happy_path(self, client):
        respx.get(f"{BASE_URL}/api/v1/trades/summary").mock(
            return_value=httpx.Response(200, json=SUMMARY_RESPONSE)
        )
        result = await client.get_trades_summary(ticker="AAPL", days=90)
        assert result["buys"] == 3
        assert result["sells"] == 2
        assert result["sentiment"] == "Bullish"

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_filters(self, client):
        respx.get(f"{BASE_URL}/api/v1/trades/summary").mock(
            return_value=httpx.Response(200, json=SUMMARY_RESPONSE)
        )
        result = await client.get_trades_summary()
        assert result["total_trades"] == 5


class TestGetMembers:
    @respx.mock
    @pytest.mark.asyncio
    async def test_happy_path(self, client):
        respx.get(f"{BASE_URL}/api/v1/members").mock(
            return_value=httpx.Response(200, json=MEMBERS_RESPONSE)
        )
        result = await client.get_members()
        assert len(result) == 2
        assert result[0]["member"] == "Nancy Pelosi"


class TestHealthCheck:
    @respx.mock
    @pytest.mark.asyncio
    async def test_healthy(self, client):
        respx.get(f"{BASE_URL}/api/v1/health").mock(
            return_value=httpx.Response(200, json=HEALTH_RESPONSE)
        )
        result = await client.health_check()
        assert result["status"] == "healthy"


class TestErrorHandling:
    @respx.mock
    @pytest.mark.asyncio
    async def test_500_raises_transient_error(self, client):
        respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(TransientError):
            await client.get_trades()

    @respx.mock
    @pytest.mark.asyncio
    async def test_404_raises_api_error(self, client):
        respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(404, text="Not Found")
        )
        with pytest.raises(APIError):
            await client.get_trades()


class TestContractValidation:
    """Verify the client passes through unexpected/partial API responses as-is."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_trades_missing_fields_in_entry(self, client):
        """Trade entry missing keys — client returns dict as-is."""
        body = {"trades": [{"member": "Pelosi"}], "total": 1}
        respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = await client.get_trades()
        assert result["trades"][0] == {"member": "Pelosi"}
        assert "ticker" not in result["trades"][0]

    @respx.mock
    @pytest.mark.asyncio
    async def test_summary_missing_buys_sells(self, client):
        """Summary without buys/sells keys."""
        body = {"total_trades": 3, "unique_members": 2, "sentiment": "Neutral"}
        respx.get(f"{BASE_URL}/api/v1/trades/summary").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = await client.get_trades_summary()
        assert "buys" not in result
        assert result["total_trades"] == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_summary_null_sentiment(self, client):
        """Sentiment is null."""
        body = {"total_trades": 2, "buys": 1, "sells": 1, "sentiment": None}
        respx.get(f"{BASE_URL}/api/v1/trades/summary").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = await client.get_trades_summary()
        assert result["sentiment"] is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_summary_empty_string_sentiment(self, client):
        """Sentiment is empty string."""
        body = {"total_trades": 2, "buys": 1, "sells": 1, "sentiment": ""}
        respx.get(f"{BASE_URL}/api/v1/trades/summary").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = await client.get_trades_summary()
        assert result["sentiment"] == ""

    @respx.mock
    @pytest.mark.asyncio
    async def test_members_partial_entry(self, client):
        """Member dict missing trade_count."""
        body = [{"member": "Pelosi"}]
        respx.get(f"{BASE_URL}/api/v1/members").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = await client.get_members()
        assert result[0] == {"member": "Pelosi"}
        assert "trade_count" not in result[0]

    @respx.mock
    @pytest.mark.asyncio
    async def test_members_null_member_name(self, client):
        """Member name is null."""
        body = [{"member": None, "trade_count": 5}]
        respx.get(f"{BASE_URL}/api/v1/members").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = await client.get_members()
        assert result[0]["member"] is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_trades_empty_trade_fields(self, client):
        """Trade with all empty strings."""
        body = {
            "trades": [{"member": "", "ticker": "", "transaction_type": "", "amount": "", "date": ""}],
            "total": 1,
        }
        respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = await client.get_trades()
        assert result["trades"][0]["member"] == ""

    @respx.mock
    @pytest.mark.asyncio
    async def test_summary_zero_total_nonzero_buys(self, client):
        """buys=3, sells=2 but total_trades=0 (inconsistent)."""
        body = {"total_trades": 0, "buys": 3, "sells": 2, "unique_members": 2, "sentiment": "Bullish"}
        respx.get(f"{BASE_URL}/api/v1/trades/summary").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = await client.get_trades_summary()
        assert result["total_trades"] == 0
        assert result["buys"] == 3


class TestRateLimitAndTimeout:
    """Rate limit (429) and timeout error handling."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self, client):
        respx.get(f"{BASE_URL}/api/v1/trades").mock(
            return_value=httpx.Response(429, text="Too Many Requests")
        )
        with pytest.raises(RateLimitError):
            await client.get_trades()

    @respx.mock
    @pytest.mark.asyncio
    async def test_timeout_raises_transient_error(self, client):
        respx.get(f"{BASE_URL}/api/v1/trades").mock(
            side_effect=httpx.ReadTimeout("read timed out")
        )
        with pytest.raises(TransientError):
            await client.get_trades()
