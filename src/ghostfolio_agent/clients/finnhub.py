import httpx
from typing import Any, cast


class FinnhubClient:
    """Async HTTP client for Finnhub API (analyst recs, earnings)."""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make authenticated GET request to Finnhub."""
        url = f"{self.BASE_URL}{path}"
        request_params = {"token": self._api_key}
        if params:
            request_params.update(params)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=request_params)
        if not response.is_success:
            raise RuntimeError(
                f"Finnhub API error: {response.status_code} {response.reason_phrase} "
                f"for {response.url} — {response.text[:500]}"
            )
        return response.json()

    async def get_analyst_recommendations(self, symbol: str) -> list[dict[str, Any]]:
        """Get analyst recommendation trends for a symbol."""
        return cast(list[dict[str, Any]], await self._get("/stock/recommendation", params={"symbol": symbol}))

    async def get_earnings_calendar(self, symbol: str) -> list[dict[str, Any]]:
        """Get upcoming earnings dates and estimates for a symbol."""
        result = await self._get("/calendar/earnings", params={"symbol": symbol})
        return cast(list[dict[str, Any]], result.get("earningsCalendar", []))
