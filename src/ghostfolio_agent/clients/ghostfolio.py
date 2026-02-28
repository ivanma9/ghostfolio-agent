import httpx
from typing import Any


class GhostfolioClient:
    """Async HTTP client for Ghostfolio REST API."""

    def __init__(self, base_url: str, access_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make authenticated GET request."""
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers, params=params)
        if not response.is_success:
            raise RuntimeError(
                f"Ghostfolio API error: {response.status_code} {response.reason_phrase} "
                f"for {response.url} — {response.text[:500]}"
            )
        return response.json()

    async def _post(self, path: str, json_data: dict) -> Any:
        """Make authenticated POST request."""
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers, json=json_data)
        if not response.is_success:
            raise RuntimeError(
                f"Ghostfolio API error: {response.status_code} {response.reason_phrase} "
                f"for {response.url} — {response.text[:500]}"
            )
        return response.json()

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
        return await self._post("/api/v1/order", order_data)
