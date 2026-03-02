from typing import Any, cast

from ghostfolio_agent.clients.base import BaseClient
from ghostfolio_agent.clients.exceptions import APIError


class FMPClient(BaseClient):
    """Async HTTP client for Financial Modeling Prep API (analyst estimates, price targets)."""

    client_name = "fmp"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        super().__init__(base_url="https://financialmodelingprep.com/stable", default_headers={})

    def _check_soft_errors(self, response_json: Any) -> None:
        """Detect error messages returned in 200 responses."""
        if isinstance(response_json, dict) and "Error Message" in response_json:
            raise APIError(
                self.client_name,
                200,
                "",
                response_json["Error Message"],
            )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make authenticated GET request to FMP, injecting apikey param."""
        merged: dict[str, Any] = {"apikey": self._api_key}
        if params:
            merged.update(params)
        return await self._request("GET", f"{self._base_url}{path}", params=merged)

    async def get_price_target_consensus(self, symbol: str) -> list[dict[str, Any]]:
        """Get analyst price target consensus (high, low, median, consensus)."""
        result = await self._get("/price-target-consensus", params={"symbol": symbol})
        return cast(list[dict[str, Any]], result if isinstance(result, list) else [])

    async def get_price_target_summary(self, symbol: str) -> list[dict[str, Any]]:
        """Get price target summary with counts and averages by time period."""
        result = await self._get("/price-target-summary", params={"symbol": symbol})
        return cast(list[dict[str, Any]], result if isinstance(result, list) else [])
