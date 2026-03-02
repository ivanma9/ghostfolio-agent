"""Congressional trading tools — search trades, get summaries, list members."""

import structlog
from langchain_core.tools import tool
from ghostfolio_agent.tools.cache import ttl_cache
from ghostfolio_agent.clients.congressional import CongressionalClient

logger = structlog.get_logger()


def create_congressional_trades_tool(congressional: CongressionalClient):
    @tool
    @ttl_cache(ttl=300)
    async def congressional_trades(
        ticker: str = "",
        member: str = "",
        days: int = 90,
        transaction_type: str = "",
    ) -> str:
        """Search congressional stock trades by ticker, member, days, or transaction type.
        Use when the user asks about what congress members are buying or selling."""
        try:
            data = await congressional.get_trades(
                ticker=ticker or None,
                member=member or None,
                days=days,
                transaction_type=transaction_type or None,
            )
        except Exception as e:
            logger.warning("congressional_trades_failed", error=str(e))
            return "Congressional trading data is temporarily unavailable."

        trades = data.get("trades", [])
        total = data.get("total", 0)

        if not trades:
            filters = []
            if ticker:
                filters.append(f"ticker={ticker}")
            if member:
                filters.append(f"member={member}")
            filter_str = f" ({', '.join(filters)})" if filters else ""
            return f"No congressional trades found in the last {days} days{filter_str}."

        lines = [f"Congressional Trades ({total} total, last {days} days):", ""]

        for t in trades[:20]:
            member_name = t.get("member") or "Unknown"
            t_ticker = t.get("ticker") or "?"
            t_type = t.get("transaction_type") or "?"
            amount = t.get("amount") or "N/A"
            t_date = t.get("date") or "N/A"
            lines.append(f"  {t_date}  {member_name:20s}  {t_type:10s}  {t_ticker:6s}  {amount}")

        if total > 20:
            lines.append(f"  ... and {total - 20} more trades")

        lines.append("[DATA_SOURCES: Congressional Trades]")
        return "\n".join(lines)

    return congressional_trades


def create_congressional_summary_tool(congressional: CongressionalClient):
    @tool
    @ttl_cache(ttl=300)
    async def congressional_trades_summary(
        ticker: str = "",
        member: str = "",
        days: int = 90,
    ) -> str:
        """Get aggregate congressional trading statistics — buy/sell counts, sentiment, and
        unique members. Use when the user wants a quick overview of congressional trading
        activity for a stock or member."""
        try:
            data = await congressional.get_trades_summary(
                ticker=ticker or None,
                member=member or None,
                days=days,
            )
        except Exception as e:
            logger.warning("congressional_summary_failed", error=str(e))
            return "Congressional trading data is temporarily unavailable."

        total = data.get("total_trades", 0)
        if total == 0:
            return f"No congressional trades found in the last {days} days."

        buys = data.get("buys") or 0
        sells = data.get("sells") or 0
        unique = data.get("unique_members") or 0
        sentiment = data.get("sentiment") or "N/A"

        header = "Congressional Trading Summary"
        if ticker:
            header += f": {ticker}"
        header += f" (last {days} days)"

        lines = [
            header,
            "",
            f"  Total Trades:    {total}",
            f"  Buys:            {buys}",
            f"  Sells:           {sells}",
            f"  Unique Members:  {unique}",
            f"  Sentiment:       {sentiment}",
            "[DATA_SOURCES: Congressional Trades]",
        ]
        return "\n".join(lines)

    return congressional_trades_summary


def create_congressional_members_tool(congressional: CongressionalClient):
    @tool
    @ttl_cache(ttl=300)
    async def congressional_members() -> str:
        """List the most active congressional traders with trade counts.
        Use when the user asks who in congress is trading the most."""
        try:
            data = await congressional.get_members()
        except Exception as e:
            logger.warning("congressional_members_failed", error=str(e))
            return "Congressional trading data is temporarily unavailable."

        if not data:
            return "No congressional member trading data available."

        members = data[:20]
        lines = [f"Most Active Congressional Traders ({len(members)} shown):", ""]

        for m in members:
            name = m.get("member") or "Unknown"
            count = m.get("trade_count") or 0
            lines.append(f"  {name:30s}  {count} trades")

        if len(data) > 20:
            lines.append(f"  ... and {len(data) - 20} more members")

        lines.append("[DATA_SOURCES: Congressional Trades]")
        return "\n".join(lines)

    return congressional_members
