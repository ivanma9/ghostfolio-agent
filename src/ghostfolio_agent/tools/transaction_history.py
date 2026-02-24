from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient


def create_transaction_history_tool(client: GhostfolioClient):
    @tool
    async def transaction_history(symbol: str = "") -> str:
        """Get the transaction history showing all buy/sell/dividend activity. Optionally filter by symbol. Use this when the user asks about their trades, transactions, purchases, or activity."""
        # client.get_orders() already unwraps the {"activities": [...]} envelope
        orders = await client.get_orders()

        # Each activity has a nested SymbolProfile object for the symbol
        if symbol:
            orders = [
                o for o in orders
                if o.get("SymbolProfile", {}).get("symbol", "").upper() == symbol.upper()
            ]

        if not orders:
            return f"No transactions found{f' for {symbol}' if symbol else ''}."

        lines = [f"Transaction History{f' for {symbol}' if symbol else ''}:", ""]
        total_invested = 0.0
        for o in orders:
            sym = o.get("SymbolProfile", {}).get("symbol", "?")
            tx_type = o.get("type", "?")
            qty = o.get("quantity", 0) or 0
            price = o.get("unitPrice", 0) or 0
            fee = o.get("fee", 0) or 0
            date_raw = o.get("date", "?")
            # Trim to date portion whether it's a full ISO string or already a date
            date = str(date_raw)[:10] if date_raw != "?" else "?"
            cost = qty * price
            if tx_type == "BUY":
                total_invested += cost
            elif tx_type == "SELL":
                total_invested -= cost
            lines.append(
                f"- {date}: {tx_type} {qty} {sym} @ ${price:.2f} (fee: ${fee:.2f}) = ${cost:,.2f}"
            )

        lines.append(f"\nTotal transactions: {len(orders)}")
        lines.append(f"Net invested: ${total_invested:,.2f}")
        return "\n".join(lines)

    return transaction_history
