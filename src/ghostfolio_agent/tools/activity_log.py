import re
from datetime import date, timezone, datetime
import structlog
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient

logger = structlog.get_logger()

# Patterns: "buy 10 AAPL at 180", "sell 5 NVDA at 900", "dividend 50 from VTI"
BUY_SELL_RE = re.compile(
    r"(buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+\$?([\d.]+)",
    re.IGNORECASE,
)
DIVIDEND_RE = re.compile(
    r"dividend\s+\$?([\d.]+)\s+from\s+(\S+)",
    re.IGNORECASE,
)


def create_activity_log_tool(client: GhostfolioClient):
    @tool
    async def activity_log(action: str) -> str:
        """Record a real BUY, SELL, or DIVIDEND activity in Ghostfolio. This writes actual data to the portfolio — not a simulation.

        Examples:
          - "buy 10 AAPL at 180"
          - "sell 5 NVDA at 900"
          - "dividend 50 from VTI"

        IMPORTANT: Always confirm the details with the user before calling this tool, as it modifies real portfolio data."""
        try:
            # Parse the action string
            buy_sell = BUY_SELL_RE.search(action)
            div = DIVIDEND_RE.search(action)

            if buy_sell:
                activity_type = buy_sell.group(1).upper()
                quantity = float(buy_sell.group(2))
                symbol = buy_sell.group(3).upper()
                unit_price = float(buy_sell.group(4))
            elif div:
                activity_type = "DIVIDEND"
                unit_price = float(div.group(1))
                symbol = div.group(2).upper()
                quantity = 1
            else:
                return (
                    "Could not parse the action. Please use one of these formats:\n"
                    '  - "buy 10 AAPL at 180"\n'
                    '  - "sell 5 NVDA at 900"\n'
                    '  - "dividend 50 from VTI"'
                )

            # Resolve symbol
            lookup = await client.lookup_symbol(symbol)
            items = lookup.get("items", [])
            if not items:
                return f"Could not find symbol '{symbol}'. Please check the ticker."

            item = items[0]
            data_source = item.get("dataSource", "YAHOO")
            resolved_symbol = item.get("symbol", symbol)
            currency = item.get("currency", "USD")

            # Get default account
            accounts = await client.get_accounts()
            if not accounts:
                return "No accounts found in Ghostfolio. Please create an account first."
            account_id = accounts[0].get("id")

            # Create the order
            order_data = {
                "accountId": account_id,
                "currency": currency,
                "dataSource": data_source,
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "fee": 0,
                "quantity": quantity,
                "symbol": resolved_symbol,
                "type": activity_type,
                "unitPrice": unit_price,
            }

            await client.create_order(order_data)

            if activity_type == "DIVIDEND":
                return f"Recorded: {activity_type} of ${unit_price:,.2f} from {resolved_symbol}"
            else:
                total = quantity * unit_price
                return f"Recorded: {activity_type} {quantity} {resolved_symbol} @ ${unit_price:,.2f} (total: ${total:,.2f})"

        except Exception as e:
            logger.error("activity_log_failed", error=str(e), action=action)
            return f"Failed to record activity: {e}"

    return activity_log
