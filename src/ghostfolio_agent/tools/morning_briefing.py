"""Morning Briefing — daily portfolio digest with notable holdings."""

import asyncio
import time
import structlog
from datetime import date
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.tools.cache import ttl_cache
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient
from ghostfolio_agent.tools.conviction_score import (
    compute_analyst_score,
    compute_price_target_score,
    compute_sentiment_score,
    compute_earnings_score,
    compute_composite,
    score_to_label,
    ANALYST_WEIGHT,
    PRICE_TARGET_WEIGHT,
    SENTIMENT_WEIGHT,
    EARNINGS_WEIGHT,
)

logger = structlog.get_logger()

MACRO_CACHE_TTL = 86400  # 24 hours in seconds

_macro_cache: dict = {
    "data": None,
    "fetched_at": None,
}


def is_macro_cache_valid(cache: dict) -> bool:
    """Check if macro cache is fresh (within TTL)."""
    if cache["data"] is None or cache["fetched_at"] is None:
        return False
    return (time.time() - cache["fetched_at"]) < MACRO_CACHE_TTL


def generate_action_items(
    market_signals: list[dict],
    earnings_watch: list[dict],
    top_movers: list[dict],
) -> list[str]:
    """Generate natural language action items from notable flags."""
    items: list[str] = []

    for signal in market_signals:
        flags = signal.get("flags", [])
        symbol = signal["symbol"]

        if "low_conviction" in flags and "negative_sentiment" in flags:
            items.append(
                f"{symbol} conviction score is {signal['conviction_score']}/100 "
                f"({signal['conviction_label']}) with bearish sentiment — review position"
            )
        elif "low_conviction" in flags:
            items.append(
                f"{symbol} conviction score is {signal['conviction_score']}/100 "
                f"({signal['conviction_label']}) — review position"
            )
        elif "negative_sentiment" in flags:
            items.append(
                f"{symbol} showing bearish sentiment — monitor closely"
            )

    for earning in earnings_watch:
        items.append(
            f"{earning['symbol']} earnings in {earning['days_until']} days — consider position sizing"
        )

    for mover in top_movers:
        if mover["daily_change"] <= -4.0:
            items.append(
                f"{mover['symbol']} down {abs(mover['daily_change']):.1f}% today — monitor closely"
            )
        elif mover["daily_change"] >= 4.0:
            items.append(
                f"{mover['symbol']} up {mover['daily_change']:.1f}% today — momentum may continue"
            )

    return items


async def _safe_fetch(coro, label: str):
    """Run a coroutine and return None on any exception."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("briefing_fetch_failed", label=label, error=str(exc))
        return None


async def _fetch_macro(alpha_vantage: AlphaVantageClient | None) -> dict:
    """Fetch macro data, using cache if valid."""
    global _macro_cache

    if is_macro_cache_valid(_macro_cache):
        return {**_macro_cache["data"], "cached": True}

    if not alpha_vantage:
        return {}

    fed, cpi, treasury = await asyncio.gather(
        _safe_fetch(alpha_vantage.get_fed_funds_rate(), "fed_funds"),
        _safe_fetch(alpha_vantage.get_cpi(), "cpi"),
        _safe_fetch(alpha_vantage.get_treasury_yield("10year"), "treasury"),
    )

    data = {}
    if fed and fed.get("data"):
        data["fed_funds_rate"] = fed["data"][0].get("value", "N/A")
    if cpi and cpi.get("data"):
        data["cpi"] = cpi["data"][0].get("value", "N/A")
    if treasury and treasury.get("data"):
        data["treasury_10y"] = treasury["data"][0].get("value", "N/A")

    _macro_cache["data"] = data
    _macro_cache["fetched_at"] = time.time()

    return {**data, "cached": False}


def create_morning_briefing_tool(
    client: GhostfolioClient,
    finnhub: FinnhubClient | None = None,
    alpha_vantage: AlphaVantageClient | None = None,
    fmp: FMPClient | None = None,
):
    @tool
    @ttl_cache(ttl=1800)
    async def morning_briefing() -> str:
        """Get a daily morning briefing with portfolio overview, top movers, upcoming earnings,
        market signals, macro snapshot, and action items. Use when the user asks for a morning
        briefing, daily update, or wants to know what's happening today with their portfolio."""

        # Fetch portfolio holdings
        try:
            data = await client.get_portfolio_holdings()
        except Exception as e:
            logger.error("briefing_holdings_failed", error=str(e))
            return "Sorry, I couldn't fetch your portfolio data for the morning briefing."

        raw_holdings = data.get("holdings", {})
        if isinstance(raw_holdings, dict):
            holdings = list(raw_holdings.values())
        else:
            holdings = list(raw_holdings)

        if not holdings:
            return "Your portfolio has no holdings — nothing to brief on."

        # Phase 1: Quick scan — quotes + earnings for all holdings
        symbols = [h.get("symbol", "") for h in holdings if h.get("symbol")]
        total_value = sum(h.get("valueInBaseCurrency", 0) or 0 for h in holdings)

        async def _none():
            return None

        quote_tasks = []
        earnings_tasks = []
        for sym in symbols:
            if finnhub:
                quote_tasks.append(_safe_fetch(finnhub.get_quote(sym), f"quote_{sym}"))
                earnings_tasks.append(_safe_fetch(finnhub.get_earnings_calendar(sym), f"earnings_{sym}"))
            else:
                quote_tasks.append(_none())
                earnings_tasks.append(_none())

        all_tasks = quote_tasks + earnings_tasks
        results = await asyncio.gather(*all_tasks) if all_tasks else []

        quotes = dict(zip(symbols, results[: len(symbols)]))
        earnings_data = dict(zip(symbols, results[len(symbols) :]))

        holdings_map = {}
        for h in holdings:
            sym = h.get("symbol", "")
            holdings_map[sym] = h

        # Daily change per holding
        daily_changes = {}
        for sym in symbols:
            q = quotes.get(sym)
            if q:
                daily_changes[sym] = q.get("dp", 0) or 0
            else:
                daily_changes[sym] = 0

        # Top 3 movers by absolute change
        sorted_movers = sorted(symbols, key=lambda s: abs(daily_changes.get(s, 0)), reverse=True)
        top_mover_symbols = sorted_movers[:3]

        top_movers = []
        for sym in top_mover_symbols:
            change = daily_changes[sym]
            if change == 0:
                continue
            q = quotes.get(sym, {})
            top_movers.append({
                "symbol": sym,
                "name": holdings_map.get(sym, {}).get("name", sym),
                "daily_change": round(change, 2),
                "current_price": q.get("c", 0) if q else 0,
                "direction": "up" if change > 0 else "down",
            })

        # Daily portfolio change
        daily_change_amount = sum(
            ((quotes.get(sym) or {}).get("d", 0) or 0) * (holdings_map.get(sym, {}).get("quantity", 0) or 0)
            for sym in symbols
        )
        daily_change_pct = (daily_change_amount / total_value * 100) if total_value > 0 else 0

        # Earnings within 7 days
        today = date.today()
        earnings_watch = []
        earnings_flagged_symbols = set()
        for sym in symbols:
            entries = earnings_data.get(sym) or []
            for entry in entries:
                date_str = entry.get("date", "")
                try:
                    edate = date.fromisoformat(date_str)
                    days_until = (edate - today).days
                    if 0 <= days_until <= 7:
                        earnings_watch.append({
                            "symbol": sym,
                            "name": holdings_map.get(sym, {}).get("name", sym),
                            "earnings_date": date_str,
                            "days_until": days_until,
                        })
                        earnings_flagged_symbols.add(sym)
                        break  # only flag first upcoming earnings per symbol
                except (ValueError, TypeError):
                    continue

        # Phase 2: Deep enrichment for notable holdings
        notable_symbols = set(top_mover_symbols) | earnings_flagged_symbols

        market_signals = []
        if notable_symbols and (alpha_vantage or finnhub or fmp):
            enrich_tasks = {}
            for sym in notable_symbols:
                sym_tasks = {}
                if alpha_vantage:
                    sym_tasks["news"] = _safe_fetch(alpha_vantage.get_news_sentiment(sym), f"news_{sym}")
                if finnhub:
                    sym_tasks["analyst"] = _safe_fetch(finnhub.get_analyst_recommendations(sym), f"analyst_{sym}")
                if fmp:
                    sym_tasks["pt"] = _safe_fetch(fmp.get_price_target_consensus(sym), f"pt_{sym}")
                enrich_tasks[sym] = sym_tasks

            flat_keys = []
            flat_coros = []
            for sym, tasks in enrich_tasks.items():
                for key, coro in tasks.items():
                    flat_keys.append((sym, key))
                    flat_coros.append(coro)

            flat_results = await asyncio.gather(*flat_coros) if flat_coros else []

            enriched = {sym: {} for sym in notable_symbols}
            for (sym, key), result in zip(flat_keys, flat_results):
                enriched[sym][key] = result

            for sym in notable_symbols:
                sym_data = enriched[sym]
                q = quotes.get(sym, {})
                market_price = q.get("c", 0) if q else 0

                components = []
                analyst_score, analyst_expl = compute_analyst_score(sym_data.get("analyst"))
                if analyst_score is not None:
                    components.append(("analyst", analyst_score, analyst_expl, ANALYST_WEIGHT))

                pt_score, pt_expl = compute_price_target_score(sym_data.get("pt"), market_price)
                if pt_score is not None:
                    components.append(("price_target", pt_score, pt_expl, PRICE_TARGET_WEIGHT))

                sent_score, sent_expl = compute_sentiment_score(sym_data.get("news"))
                if sent_score is not None:
                    components.append(("sentiment", sent_score, sent_expl, SENTIMENT_WEIGHT))

                earn_score, earn_expl = compute_earnings_score(earnings_data.get(sym))
                components.append(("earnings", earn_score, earn_expl, EARNINGS_WEIGHT))

                composite, label, _ = compute_composite(components)

                sentiment_label = "Neutral"
                if sym_data.get("news"):
                    bullish_labels = {"Bullish", "Somewhat_Bullish", "Somewhat-Bullish"}
                    bearish_labels = {"Bearish", "Somewhat_Bearish", "Somewhat-Bearish"}
                    articles = sym_data["news"]
                    bullish_count = sum(1 for a in articles if a.get("overall_sentiment_label") in bullish_labels)
                    bearish_count = sum(1 for a in articles if a.get("overall_sentiment_label") in bearish_labels)
                    if bearish_count > bullish_count:
                        sentiment_label = "Bearish"
                    elif bullish_count > bearish_count:
                        sentiment_label = "Bullish"

                analyst_consensus = "N/A"
                analyst_data_val = sym_data.get("analyst")
                if analyst_data_val and len(analyst_data_val) > 0:
                    entry = analyst_data_val[0]
                    total_analysts = sum(entry.get(k, 0) for k in ["strongBuy", "buy", "hold", "sell", "strongSell"])
                    bullish = entry.get("strongBuy", 0) + entry.get("buy", 0)
                    if total_analysts > 0:
                        ratio = bullish / total_analysts
                        if ratio >= 0.7:
                            analyst_consensus = "Strong Buy"
                        elif ratio >= 0.5:
                            analyst_consensus = "Buy"
                        elif ratio >= 0.3:
                            analyst_consensus = "Hold"
                        else:
                            analyst_consensus = "Sell"

                flags = []
                if composite is not None and composite < 40:
                    flags.append("low_conviction")
                if sentiment_label == "Bearish":
                    flags.append("negative_sentiment")
                if sentiment_label == "Bullish":
                    flags.append("positive_sentiment")

                signal = {
                    "symbol": sym,
                    "name": holdings_map.get(sym, {}).get("name", sym),
                    "sentiment_score": sent_score,
                    "sentiment_label": sentiment_label,
                    "analyst_consensus": analyst_consensus,
                    "conviction_score": composite,
                    "conviction_label": label if composite is not None else "N/A",
                    "flags": flags,
                }
                market_signals.append(signal)

        # Macro snapshot
        macro = await _fetch_macro(alpha_vantage)

        # Action items
        action_items = generate_action_items(market_signals, earnings_watch, top_movers)

        # Format output
        lines = [
            f"Morning Briefing: {today.strftime('%B %d, %Y')}",
            "",
            "Portfolio Overview:",
            f"  Total Value: ${total_value:,.2f}",
            f"  Daily Change: {daily_change_pct:+.1f}% (${daily_change_amount:+,.2f})",
            f"  Holdings: {len(holdings)}",
            "",
        ]

        lines.append("Top Movers:")
        if top_movers:
            for m in top_movers:
                arrow = "▲" if m["direction"] == "up" else "▼"
                lines.append(
                    f"  {arrow} {m['symbol']} ({m['name']}): {m['daily_change']:+.1f}% @ ${m['current_price']:,.2f}"
                )
        else:
            lines.append("  No significant movers today")
        lines.append("")

        lines.append("Earnings Watch:")
        if earnings_watch:
            for e in earnings_watch:
                lines.append(f"  {e['symbol']} ({e['name']}): {e['earnings_date']} (in {e['days_until']} days)")
        else:
            lines.append("  No upcoming earnings this week")
        lines.append("")

        lines.append("Market Signals:")
        if market_signals:
            for s in market_signals:
                conv_str = f"{s['conviction_score']}/100 ({s['conviction_label']})" if s["conviction_score"] is not None else "N/A"
                lines.append(
                    f"  {s['symbol']} ({s['name']}): Sentiment={s['sentiment_label']}, "
                    f"Analyst={s['analyst_consensus']}, Conviction={conv_str}"
                )
                if s["flags"]:
                    lines.append(f"    Flags: {', '.join(s['flags'])}")
        else:
            lines.append("  No notable signals")
        lines.append("")

        lines.append("Macro Snapshot:")
        if macro:
            fed = macro.get("fed_funds_rate", "N/A")
            cpi_val = macro.get("cpi", "N/A")
            treasury = macro.get("treasury_10y", "N/A")
            cached_str = " (cached)" if macro.get("cached") else ""
            lines.append(f"  Fed Funds Rate: {fed}%{cached_str}")
            lines.append(f"  CPI: {cpi_val}%")
            lines.append(f"  10Y Treasury Yield: {treasury}%")
        else:
            lines.append("  Macro data not available")
        lines.append("")

        lines.append("Action Items:")
        if action_items:
            for item in action_items:
                lines.append(f"  • {item}")
        else:
            lines.append("  No action items — portfolio looks stable")

        return "\n".join(lines)

    return morning_briefing
