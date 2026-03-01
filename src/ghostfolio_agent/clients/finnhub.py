from typing import Any, cast

from ghostfolio_agent.clients.base import BaseClient


class FinnhubClient(BaseClient):
    """Async HTTP client for Finnhub API (analyst recs, earnings)."""

    client_name = "finnhub"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        super().__init__(base_url="https://finnhub.io/api/v1", default_headers={})

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make authenticated GET request to Finnhub, injecting token param."""
        merged_params = {"token": self._api_key}
        if params:
            merged_params.update(params)
        return await self._request("GET", f"{self._base_url}{path}", params=merged_params)

    async def get_analyst_recommendations(self, symbol: str) -> list[dict[str, Any]]:
        """Get analyst recommendation trends for a symbol."""
        return cast(list[dict[str, Any]], await self._get("/stock/recommendation", params={"symbol": symbol}))

    async def get_earnings_calendar(self, symbol: str) -> list[dict[str, Any]]:
        """Get upcoming earnings dates and estimates for a symbol."""
        result = await self._get("/calendar/earnings", params={"symbol": symbol})
        return cast(list[dict[str, Any]], result.get("earningsCalendar", []))

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get real-time quote for a symbol.

        Returns dict with keys: c (current), h (high), l (low), o (open),
        pc (prev close), dp (change %), d (change).
        """
        return cast(dict[str, Any], await self._get("/quote", params={"symbol": symbol}))
