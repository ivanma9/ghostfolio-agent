import structlog
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.tools.cache import ttl_cache

logger = structlog.get_logger()


def create_stock_quote_tool(client: GhostfolioClient, finnhub: FinnhubClient | None = None):
    @tool
    @ttl_cache(ttl=60)
    async def stock_quote(symbol: str) -> str:
        """Get current stock quote — price, day range, and change. Use this when the user asks for a stock's price or wants to check a price before trading."""
        # Resolve symbol via Ghostfolio lookup
        try:
            lookup = await client.lookup_symbol(symbol)
        except Exception as e:
            return f"Error looking up {symbol}: {e}"

        items = lookup.get("items", [])
        if not items:
            return f"Symbol '{symbol}' not found. Please check the ticker or company name."

        # Prefer exact ticker match first, then USD equities from YAHOO
        upper_symbol = symbol.upper().strip()
        best = items[0]
        # Pass 1: exact ticker match with USD STOCK YAHOO
        for item in items:
            if (
                item.get("symbol", "").upper() == upper_symbol
                and item.get("currency") == "USD"
                and item.get("dataSource") == "YAHOO"
            ):
                best = item
                break
        else:
            # Pass 2: any USD STOCK from YAHOO
            for item in items:
                if (
                    item.get("currency") == "USD"
                    and item.get("assetSubClass") == "STOCK"
                    and item.get("dataSource") == "YAHOO"
                ):
                    best = item
                    break

        data_source = best.get("dataSource", "YAHOO")
        resolved_symbol = best.get("symbol", symbol)
        name = best.get("name", resolved_symbol)

        # Get Ghostfolio price as fallback
        ghostfolio_price = None
        try:
            sym_data = await client.get_symbol(data_source, resolved_symbol)
            ghostfolio_price = sym_data.get("marketPrice")
        except Exception as e:
            logger.warning("stock_quote_ghostfolio_price_failed", symbol=resolved_symbol, error=str(e))

        # Try Finnhub for richer quote data
        if finnhub:
            try:
                q = await finnhub.get_quote(resolved_symbol)
                current = q.get("c")
                if current and current > 0:
                    high = q.get("h", 0)
                    low = q.get("l", 0)
                    open_price = q.get("o", 0)
                    prev_close = q.get("pc", 0)
                    change = q.get("d", 0)
                    change_pct = q.get("dp", 0)
                    sign = "+" if change >= 0 else ""

                    lines = [
                        f"{resolved_symbol} — {name}",
                        f"  Price:      ${current:,.2f}  ({sign}{change:,.2f}, {sign}{change_pct:.2f}%)",
                        f"  Day Range:  ${low:,.2f} – ${high:,.2f}",
                        f"  Open:       ${open_price:,.2f}",
                        f"  Prev Close: ${prev_close:,.2f}",
                    ]
                    return "\n".join(lines)
            except Exception as e:
                logger.warning("stock_quote_finnhub_failed", symbol=resolved_symbol, error=str(e))

        # Fallback to Ghostfolio price only
        if ghostfolio_price:
            return f"{resolved_symbol} — {name}\n  Price: ${ghostfolio_price:,.2f}"

        return f"Could not retrieve price for {resolved_symbol}."

    return stock_quote
