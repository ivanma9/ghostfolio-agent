from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient


def create_portfolio_summary_tool(client: GhostfolioClient):
    @tool
    async def portfolio_summary() -> str:
        """Get a summary of the user's portfolio including all holdings, their current values, allocations, and total portfolio value. Use this when the user asks about their portfolio, holdings, positions, or allocation."""
        data = await client.get_portfolio_holdings()

        # The Ghostfolio API returns holdings as a dict keyed by symbol,
        # e.g. {"holdings": {"AAPL": {...}, "MSFT": {...}}}
        raw_holdings = data.get("holdings", {})
        if isinstance(raw_holdings, dict):
            holdings = list(raw_holdings.values())
        else:
            # Fallback: already a list
            holdings = list(raw_holdings)

        if not holdings:
            return "No holdings found in portfolio."

        lines = ["Portfolio Summary:", ""]
        total_value = 0.0
        for h in holdings:
            symbol = h.get("symbol", "?")
            name = h.get("name", symbol) or symbol
            qty = h.get("quantity", 0) or 0
            value = h.get("valueInBaseCurrency", 0) or 0
            price = h.get("marketPrice", 0) or 0
            alloc = h.get("allocationInPercentage", 0) or 0
            total_value += value
            lines.append(
                f"- {symbol} ({name}): {qty} shares @ ${price:.2f} = ${value:,.2f} ({alloc * 100:.1f}%)"
            )

        lines.append(f"\nTotal Portfolio Value: ${total_value:,.2f}")
        return "\n".join(lines)

    return portfolio_summary
