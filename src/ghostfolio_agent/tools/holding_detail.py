import asyncio
import structlog
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient

logger = structlog.get_logger()


async def _safe_fetch(coro, label: str):
    """Run a coroutine and return None on any exception."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("enrichment_fetch_failed", label=label, error=str(exc))
        return None


def _format_earnings(earnings: list[dict] | None) -> list[str]:
    """Format Finnhub earnings calendar entries (up to 3)."""
    if not earnings:
        return []
    lines = ["", "Upcoming Earnings:"]
    for entry in earnings[:3]:
        date = entry.get("date", "N/A")
        eps_est = entry.get("epsEstimate")
        eps_act = entry.get("epsActual")
        eps_est_str = f"${eps_est:.2f}" if eps_est is not None else "N/A"
        eps_act_str = f"${eps_act:.2f}" if eps_act is not None else "N/A"
        lines.append(f"  {date}  EPS Est: {eps_est_str}  EPS Actual: {eps_act_str}")
    return lines


def _format_analyst(analyst: list[dict] | None) -> list[str]:
    """Format Finnhub analyst recommendation trends (most recent entry)."""
    if not analyst:
        return []
    entry = analyst[0]
    period = entry.get("period", "N/A")
    strong_buy = entry.get("strongBuy", 0)
    buy = entry.get("buy", 0)
    hold = entry.get("hold", 0)
    sell = entry.get("sell", 0)
    strong_sell = entry.get("strongSell", 0)
    return [
        "",
        f"Analyst Consensus ({period}):",
        f"  Strong Buy: {strong_buy}  Buy: {buy}  Hold: {hold}  Sell: {sell}  Strong Sell: {strong_sell}",
    ]


def _format_congressional(trades: list[dict] | None) -> list[str]:
    """Format Finnhub congressional trading activity (up to 5 entries)."""
    if not trades:
        return []
    lines = ["", "Congressional Trading:"]
    for trade in trades[:5]:
        rep = trade.get("representative", "Unknown")
        tx_type = trade.get("transactionType", "N/A")
        amount = trade.get("transactionAmount", "N/A")
        date = trade.get("transactionDate", "N/A")
        lines.append(f"  {date}  {rep}: {tx_type}  {amount}")
    return lines


def _format_news_sentiment(news: list[dict] | None) -> list[str]:
    """Format Alpha Vantage news sentiment entries (up to 5)."""
    if not news:
        return []
    lines = ["", "News Sentiment:"]
    for item in news[:5]:
        title = item.get("title", "")[:80]
        sentiment = item.get("overall_sentiment_label", "N/A")
        source = item.get("source", "N/A")
        lines.append(f"  [{sentiment}] {title}  ({source})")
    return lines


def _format_insider_trading(trades: list[dict] | None) -> list[str]:
    """Format FMP insider trading entries (up to 5)."""
    if not trades:
        return []
    lines = ["", "Insider Trading:"]
    for trade in trades[:5]:
        name = trade.get("reportingName", "Unknown")
        tx_type = trade.get("transactionType", "N/A")
        shares = trade.get("securitiesTransacted", 0)
        price = trade.get("price", 0)
        date = trade.get("transactionDate", "N/A")
        lines.append(f"  {date}  {name}: {tx_type}  {shares:,} shares @ ${price:.2f}")
    return lines


def create_holding_detail_tool(
    client: GhostfolioClient,
    finnhub: FinnhubClient | None = None,
    alpha_vantage: AlphaVantageClient | None = None,
    fmp: FMPClient | None = None,
):
    @tool
    async def holding_detail(symbol: str) -> str:
        """Get a deep dive into a specific portfolio holding — cost basis, P&L, performance,
        and transaction history. When 3rd-party clients are configured, also includes external
        intelligence: upcoming earnings, analyst consensus, congressional trading activity,
        news sentiment, and insider trading. Use when the user asks about a specific position
        they own, e.g. 'How is my AAPL doing?' or 'Tell me about my TSLA position'."""
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

        # --- Parallel enrichment fetches ---
        enrichment_tasks = []
        task_labels = []

        if finnhub:
            enrichment_tasks.append(_safe_fetch(finnhub.get_earnings_calendar(resolved_symbol), "finnhub_earnings"))
            task_labels.append("earnings")
            enrichment_tasks.append(_safe_fetch(finnhub.get_analyst_recommendations(resolved_symbol), "finnhub_analyst"))
            task_labels.append("analyst")
            enrichment_tasks.append(_safe_fetch(finnhub.get_congressional_trading(resolved_symbol), "finnhub_congressional"))
            task_labels.append("congressional")

        if alpha_vantage:
            enrichment_tasks.append(_safe_fetch(alpha_vantage.get_news_sentiment(resolved_symbol), "av_news"))
            task_labels.append("news")

        if fmp:
            enrichment_tasks.append(_safe_fetch(fmp.get_insider_trading(resolved_symbol), "fmp_insider"))
            task_labels.append("insider")

        if enrichment_tasks:
            results = await asyncio.gather(*enrichment_tasks)
            enrichment = dict(zip(task_labels, results))

            lines.extend(_format_earnings(enrichment.get("earnings")))
            lines.extend(_format_analyst(enrichment.get("analyst")))
            lines.extend(_format_congressional(enrichment.get("congressional")))
            lines.extend(_format_news_sentiment(enrichment.get("news")))
            lines.extend(_format_insider_trading(enrichment.get("insider")))

        return "\n".join(lines)

    return holding_detail
