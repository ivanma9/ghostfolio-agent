import asyncio
import structlog
from datetime import date
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


def _format_price_targets(consensus: list[dict] | None, summary: list[dict] | None) -> list[str]:
    """Format FMP price target consensus and summary."""
    lines: list[str] = []
    if consensus:
        c = consensus[0]
        lines.extend([
            "",
            "Price Targets:",
            f"  Consensus: ${c.get('targetConsensus', 0):,.2f}  "
            f"Median: ${c.get('targetMedian', 0):,.2f}  "
            f"High: ${c.get('targetHigh', 0):,.2f}  "
            f"Low: ${c.get('targetLow', 0):,.2f}",
        ])
    if summary:
        s = summary[0]
        last_mo = s.get("lastMonthCount", 0)
        last_mo_avg = s.get("lastMonthAvgPriceTarget", 0)
        last_q = s.get("lastQuarterCount", 0)
        last_q_avg = s.get("lastQuarterAvgPriceTarget", 0)
        if not consensus:
            lines.extend(["", "Price Targets:"])
        lines.append(f"  Last Month: {last_mo} analysts, avg ${last_mo_avg:,.2f}")
        lines.append(f"  Last Quarter: {last_q} analysts, avg ${last_q_avg:,.2f}")
    return lines


def _format_smart_summary(market_price: float, enrichment: dict) -> list[str]:
    """Compute actionable signals from enrichment data and return formatted lines."""
    signals: list[str] = []

    # 1. Implied Upside/Downside from FMP price target consensus
    pt_consensus = enrichment.get("pt_consensus")
    if pt_consensus and market_price:
        consensus = pt_consensus[0].get("targetConsensus", 0)
        if consensus and consensus != market_price:
            pct = (consensus - market_price) / market_price * 100
            if consensus > market_price:
                signals.append(f"  Implied Upside: +{pct:.1f}% (target ${consensus:,.2f})")
            else:
                signals.append(f"  Implied Downside: {pct:.1f}% (target ${consensus:,.2f})")

    # 2. Analyst Signal from Finnhub recommendations
    analyst = enrichment.get("analyst")
    if analyst:
        entry = analyst[0]
        strong_buy = entry.get("strongBuy", 0)
        buy = entry.get("buy", 0)
        hold = entry.get("hold", 0)
        sell = entry.get("sell", 0)
        strong_sell = entry.get("strongSell", 0)
        bullish = strong_buy + buy
        bearish = sell + strong_sell
        total = bullish + hold + bearish
        if total > 0:
            bullish_ratio = bullish / total
            bearish_ratio = bearish / total
            if bullish_ratio >= 0.7:
                label = "Strong Buy"
            elif bullish_ratio >= 0.5:
                label = "Buy"
            elif bearish_ratio >= 0.5:
                label = "Sell"
            else:
                label = "Hold"
            signals.append(f"  Analyst Signal: {label} ({bullish} of {total} analysts bullish)")

    # 3. Sentiment Score from Alpha Vantage news
    news = enrichment.get("news")
    if news:
        bullish_labels = {"Bullish", "Somewhat_Bullish", "Somewhat-Bullish"}
        bearish_labels = {"Bearish", "Somewhat_Bearish", "Somewhat-Bearish"}
        total = len(news)
        bullish_count = sum(1 for a in news if a.get("overall_sentiment_label") in bullish_labels)
        bearish_count = sum(1 for a in news if a.get("overall_sentiment_label") in bearish_labels)
        if bullish_count > bearish_count:
            signals.append(f"  Sentiment: Bullish ({bullish_count} of {total} articles positive)")
        elif bearish_count > bullish_count:
            signals.append(f"  Sentiment: Bearish ({bearish_count} of {total} articles negative)")
        else:
            signals.append(f"  Sentiment: Neutral ({total} articles reviewed)")

    # 4. Earnings Proximity — within 14 days
    earnings = enrichment.get("earnings")
    if earnings:
        today = date.today()
        for entry in earnings:
            date_str = entry.get("date", "")
            try:
                earnings_date = date.fromisoformat(date_str)
                days_until = (earnings_date - today).days
                if 0 <= days_until <= 14:
                    signals.append(f"  Earnings Alert: Reporting in {days_until} days ({date_str})")
                    break
            except (ValueError, TypeError):
                continue

    if not signals:
        return []
    return ["", "Smart Summary:"] + signals


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
        intelligence: upcoming earnings, analyst consensus, news sentiment, and price targets.
        Use when the user asks about a specific position they own, e.g. 'How is my AAPL doing?'
        or 'Tell me about my TSLA position'."""
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

        if alpha_vantage:
            enrichment_tasks.append(_safe_fetch(alpha_vantage.get_news_sentiment(resolved_symbol), "av_news"))
            task_labels.append("news")

        if fmp:
            enrichment_tasks.append(_safe_fetch(fmp.get_price_target_consensus(resolved_symbol), "fmp_pt_consensus"))
            task_labels.append("pt_consensus")
            enrichment_tasks.append(_safe_fetch(fmp.get_price_target_summary(resolved_symbol), "fmp_pt_summary"))
            task_labels.append("pt_summary")

        if enrichment_tasks:
            results = await asyncio.gather(*enrichment_tasks)
            enrichment = dict(zip(task_labels, results))

            lines.extend(_format_earnings(enrichment.get("earnings")))
            lines.extend(_format_analyst(enrichment.get("analyst")))
            lines.extend(_format_news_sentiment(enrichment.get("news")))
            lines.extend(_format_price_targets(enrichment.get("pt_consensus"), enrichment.get("pt_summary")))
            lines.extend(_format_smart_summary(market_price, enrichment))

        return "\n".join(lines)

    return holding_detail
