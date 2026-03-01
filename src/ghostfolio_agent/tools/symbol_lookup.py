import structlog
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.tools.cache import ttl_cache

logger = structlog.get_logger()


def create_symbol_lookup_tool(client: GhostfolioClient):
    @tool
    @ttl_cache(ttl=3600)
    async def symbol_lookup(query: str) -> str:
        """Look up a stock, ETF, or cryptocurrency by name or ticker symbol. Use this when the user asks about a specific security, wants to know what a ticker is, or needs current price information."""
        try:
            data = await client.lookup_symbol(query)
        except Exception as e:
            logger.error("symbol_lookup_failed", error=str(e), query=query)
            return f"Sorry, I couldn't look up '{query}' right now. Please try again later."
        items = data.get("items", [])

        if not items:
            return f"No results found for '{query}'."

        lines = [f"Symbol Lookup Results for '{query}':", ""]
        for item in items[:10]:  # limit to 10 results
            symbol = item.get("symbol", "?")
            name = item.get("name", "?") or "?"
            source = item.get("dataSource", "?")
            currency = item.get("currency", "?")
            asset_class = item.get("assetClass", "?")
            asset_sub = item.get("assetSubClass", "?")
            lines.append(
                f"- {symbol}: {name} ({asset_class}/{asset_sub}) — {currency} via {source}"
            )

        if len(items) > 10:
            lines.append(f"\n... and {len(items) - 10} more results")

        return "\n".join(lines)

    return symbol_lookup
