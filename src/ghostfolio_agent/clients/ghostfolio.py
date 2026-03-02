from typing import Any

from ghostfolio_agent.clients.base import BaseClient


class GhostfolioClient(BaseClient):
    """Async HTTP client for Ghostfolio REST API."""

    client_name = "ghostfolio"
    retryable = True
    max_retries = 2

    def __init__(self, base_url: str, access_token: str) -> None:
        super().__init__(
            base_url=base_url,
            default_headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

    async def get_portfolio_holdings(self) -> dict[str, Any]:
        """Get portfolio holdings with values and allocations."""
        return await self._get("/api/v1/portfolio/holdings")

    async def get_portfolio_details(self) -> dict[str, Any]:
        """Get detailed portfolio breakdown."""
        return await self._get("/api/v1/portfolio/details")

    async def get_orders(self) -> list[dict[str, Any]]:
        """Get all transactions/orders."""
        result = await self._get("/api/v1/order")
        return result.get("activities", [])

    async def lookup_symbol(self, query: str) -> dict[str, Any]:
        """Search for symbols by name or ticker."""
        return await self._get("/api/v1/symbol/lookup", params={"query": query})

    async def get_symbol(self, data_source: str, symbol: str) -> dict[str, Any]:
        """Get details for a specific symbol."""
        return await self._get(f"/api/v1/symbol/{data_source}/{symbol}")

    async def get_portfolio_performance(self, date_range: str = "max") -> dict[str, Any]:
        """Get portfolio performance for a date range. Range: 1d, 1w, 1m, 3m, 6m, 1y, ytd, max."""
        return await self._get("/api/v2/portfolio/performance", params={"range": date_range})

    async def get_holding(self, data_source: str, symbol: str) -> dict[str, Any]:
        """Get detailed info for a specific portfolio holding."""
        return await self._get(f"/api/v1/portfolio/holding/{data_source}/{symbol}")

    async def get_accounts(self) -> list[dict[str, Any]]:
        """Get all accounts."""
        result = await self._get("/api/v1/account")
        return result.get("accounts", result) if isinstance(result, dict) else result

    async def create_order(self, order_data: dict) -> dict[str, Any]:
        """Create a new order/activity."""
        return await self._post("/api/v1/order", json_data=order_data)

    async def get_benchmarks(self) -> dict[str, Any]:
        """Get list of available benchmarks with performance and trend data."""
        return await self._get("/api/v1/benchmarks")

    async def get_benchmark_detail(
        self,
        data_source: str,
        symbol: str,
        start_date: str,
        date_range: str = "max",
    ) -> dict[str, Any]:
        """Get historical benchmark data for a symbol from a start date.

        Args:
            data_source: Data source identifier (e.g. "YAHOO").
            symbol: Ticker symbol (e.g. "SPY").
            start_date: ISO date string for the start of the comparison (e.g. "2020-01-01").
            date_range: Range filter — 1d, 1w, 1m, 3m, 6m, 1y, ytd, max (default "max").

        Returns:
            Dict with "marketData" key containing list of {date, value} objects where
            value is percentage change from start_date (already multiplied by 100).
        """
        return await self._get(
            f"/api/v1/benchmarks/{data_source}/{symbol}/{start_date}",
            params={"range": date_range},
        )
