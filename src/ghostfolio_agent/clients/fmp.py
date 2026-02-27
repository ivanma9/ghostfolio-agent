import httpx
from typing import Any, cast


class FMPClient:
    """Async HTTP client for Financial Modeling Prep API (insider trading, analyst estimates)."""

    BASE_URL = "https://financialmodelingprep.com/api"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make authenticated GET request to FMP."""
        url = f"{self.BASE_URL}{path}"
        request_params: dict[str, Any] = {"apikey": self._api_key}
        if params:
            request_params.update(params)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=request_params)
        if not response.is_success:
            raise RuntimeError(
                f"FMP API error: {response.status_code} {response.reason_phrase} "
                f"for {response.url} — {response.text[:500]}"
            )
        return response.json()

    async def get_insider_trading(self, symbol: str) -> list[dict[str, Any]]:
        """Get insider trading activity for a symbol."""
        result = await self._get("/v4/insider-trading", params={"symbol": symbol})
        return cast(list[dict[str, Any]], result if isinstance(result, list) else [])

    async def get_analyst_estimates(self, symbol: str) -> list[dict[str, Any]]:
        """Get analyst estimates/consensus for a symbol."""
        result = await self._get(f"/v3/analyst-estimates/{symbol}")
        return cast(list[dict[str, Any]], result if isinstance(result, list) else [])
