from typing import Any, cast

from ghostfolio_agent.clients.base import BaseClient
from ghostfolio_agent.clients.exceptions import RateLimitError


class AlphaVantageClient(BaseClient):
    """Async HTTP client for Alpha Vantage API (news sentiment, macro indicators)."""

    client_name = "alpha_vantage"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        super().__init__(base_url="https://www.alphavantage.co", default_headers={})

    def _check_soft_errors(self, response_json: Any) -> None:
        """Detect rate limit soft errors in 200 responses."""
        if isinstance(response_json, dict) and (
            "Note" in response_json or "Information" in response_json
        ):
            raise RateLimitError(
                self.client_name,
                200,
                "",
                response_json.get("Note") or response_json.get("Information") or "Rate limit exceeded",
            )

    async def _query(self, params: dict[str, Any]) -> Any:
        """Make authenticated GET request to Alpha Vantage /query endpoint."""
        merged = {**params, "apikey": self._api_key}
        return await self._request("GET", f"{self._base_url}/query", params=merged)

    async def get_news_sentiment(self, ticker: str) -> list[dict[str, Any]]:
        """Get news sentiment for a ticker symbol."""
        result = await self._query({"function": "NEWS_SENTIMENT", "tickers": ticker})
        return cast(list[dict[str, Any]], result.get("feed", []))

    async def get_fed_funds_rate(self) -> list[dict[str, Any]]:
        """Get Federal Funds effective rate (daily)."""
        result = await self._query({"function": "FEDERAL_FUNDS_RATE", "interval": "daily"})
        return cast(list[dict[str, Any]], result.get("data", []))

    async def get_cpi(self) -> list[dict[str, Any]]:
        """Get Consumer Price Index (monthly)."""
        result = await self._query({"function": "CPI", "interval": "monthly"})
        return cast(list[dict[str, Any]], result.get("data", []))

    async def get_treasury_yield(self, maturity: str = "10year") -> list[dict[str, Any]]:
        """Get Treasury Yield (daily). Maturity: 3month, 2year, 5year, 7year, 10year, 30year."""
        result = await self._query({
            "function": "TREASURY_YIELD",
            "interval": "daily",
            "maturity": maturity,
        })
        return cast(list[dict[str, Any]], result.get("data", []))
