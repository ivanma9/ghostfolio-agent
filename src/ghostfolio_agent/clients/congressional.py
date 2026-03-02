from typing import Any

from ghostfolio_agent.clients.base import BaseClient


class CongressionalClient(BaseClient):
    """Async HTTP client for the Congressional Trading API (private networking)."""

    client_name = "congressional"

    def __init__(self, base_url: str) -> None:
        super().__init__(base_url=base_url, default_headers={})

    async def get_trades(
        self,
        ticker: str | None = None,
        member: str | None = None,
        days: int | None = None,
        transaction_type: str | None = None,
    ) -> dict[str, Any]:
        """Get congressional trades, optionally filtered."""
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if member:
            params["member"] = member
        if days is not None:
            params["days"] = days
        if transaction_type:
            params["transaction_type"] = transaction_type
        return await self._get("/api/v1/trades", params=params)

    async def get_trades_summary(
        self,
        ticker: str | None = None,
        member: str | None = None,
        days: int | None = None,
    ) -> dict[str, Any]:
        """Get aggregate congressional trading statistics."""
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if member:
            params["member"] = member
        if days is not None:
            params["days"] = days
        return await self._get("/api/v1/trades/summary", params=params)

    async def get_members(self) -> list[dict[str, Any]]:
        """List active congressional traders with trade counts."""
        return await self._get("/api/v1/members")

    async def health_check(self) -> dict[str, Any]:
        """Check API health status."""
        return await self._get("/api/v1/health")
