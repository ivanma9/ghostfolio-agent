import httpx
from typing import Any, cast


class AlphaVantageClient:
    """Async HTTP client for Alpha Vantage API (news sentiment, macro indicators)."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def _get(self, params: dict[str, Any]) -> Any:
        """Make authenticated GET request to Alpha Vantage."""
        request_params = {**params, "apikey": self._api_key}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(self.BASE_URL, params=request_params)
        if not response.is_success:
            raise RuntimeError(
                f"Alpha Vantage API error: {response.status_code} {response.reason_phrase} "
                f"— {response.text[:500]}"
            )
        return response.json()

    async def get_news_sentiment(self, ticker: str) -> list[dict[str, Any]]:
        """Get news sentiment for a ticker symbol."""
        result = await self._get({"function": "NEWS_SENTIMENT", "tickers": ticker})
        return cast(list[dict[str, Any]], result.get("feed", []))

    async def get_fed_funds_rate(self) -> list[dict[str, Any]]:
        """Get Federal Funds effective rate (daily)."""
        result = await self._get({"function": "FEDERAL_FUNDS_RATE", "interval": "daily"})
        return cast(list[dict[str, Any]], result.get("data", []))

    async def get_cpi(self) -> list[dict[str, Any]]:
        """Get Consumer Price Index (monthly)."""
        result = await self._get({"function": "CPI", "interval": "monthly"})
        return cast(list[dict[str, Any]], result.get("data", []))

    async def get_treasury_yield(self, maturity: str = "10year") -> list[dict[str, Any]]:
        """Get Treasury Yield (daily). Maturity: 3month, 2year, 5year, 7year, 10year, 30year."""
        result = await self._get({
            "function": "TREASURY_YIELD",
            "interval": "daily",
            "maturity": maturity,
        })
        return cast(list[dict[str, Any]], result.get("data", []))
