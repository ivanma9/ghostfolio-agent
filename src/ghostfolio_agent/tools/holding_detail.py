import structlog
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient

logger = structlog.get_logger()


def create_holding_detail_tool(client: GhostfolioClient):
    @tool
    async def holding_detail(symbol: str) -> str:
        """Get a deep dive into a specific portfolio holding — cost basis, P&L, performance, and transaction history. Use when the user asks about a specific position they own, e.g. 'How is my AAPL doing?' or 'Tell me about my TSLA position'."""
        try:
            # Resolve dataSource via symbol lookup
            lookup = await client.lookup_symbol(symbol)
            items = lookup.get("items", [])
            if not items:
                return f"Could not find symbol '{symbol}'. Please check the ticker and try again."

            data_source = items[0].get("dataSource", "YAHOO")
            resolved_symbol = items[0].get("symbol", symbol)

            holding = await client.get_holding(data_source, resolved_symbol)
        except Exception as e:
            logger.error("holding_detail_failed", error=str(e), symbol=symbol)
            return f"Sorry, I couldn't get details for '{symbol}'. It may not be in your portfolio, or the API is unavailable."

        # Extract key fields
        name = holding.get("name", symbol)
        quantity = holding.get("quantity", 0)
        market_price = holding.get("marketPrice", 0)
        currency = holding.get("currency", "USD")
        average_price = holding.get("averagePrice", 0)
        investment = holding.get("investment", 0)
        value = holding.get("value", 0)
        net_performance = holding.get("netPerformance", 0)
        net_performance_pct = holding.get("netPerformancePercent", 0)
        dividend = holding.get("dividend", 0)
        first_buy = holding.get("firstBuyDate", "N/A")
        transaction_count = holding.get("transactionCount", 0)

        lines = [
            f"Holding Detail: {name} ({resolved_symbol})",
            "",
            f"  Quantity:        {quantity}",
            f"  Market Price:    ${market_price:,.2f} {currency}",
            f"  Average Cost:    ${average_price:,.2f}",
            f"  Total Invested:  ${investment:,.2f}",
            f"  Current Value:   ${value:,.2f}",
            "",
            f"  Unrealized P&L:  ${net_performance:,.2f} ({net_performance_pct * 100:+.1f}%)",
        ]

        if dividend:
            lines.append(f"  Dividends:       ${dividend:,.2f}")

        lines.extend([
            "",
            f"  First Buy:       {first_buy}",
            f"  Transactions:    {transaction_count}",
        ])

        return "\n".join(lines)

    return holding_detail
