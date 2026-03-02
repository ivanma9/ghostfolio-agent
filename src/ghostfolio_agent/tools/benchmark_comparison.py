import asyncio
import structlog
from datetime import date, timedelta
from langchain_core.tools import tool

from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.tools.cache import ttl_cache
from ghostfolio_agent.utils import safe_fetch

logger = structlog.get_logger()

PERIOD_TO_START = {
    "1d": lambda: (date.today() - timedelta(days=1)).isoformat(),
    "ytd": lambda: date(date.today().year, 1, 1).isoformat(),
    "mtd": lambda: date(date.today().year, date.today().month, 1).isoformat(),
    "1y": lambda: (date.today() - timedelta(days=365)).isoformat(),
    "5y": lambda: (date.today() - timedelta(days=5 * 365)).isoformat(),
    "max": lambda: "2000-01-01",
}

PERIOD_TO_RANGE = {
    "1d": "1d",
    "ytd": "ytd",
    "mtd": "1m",
    "1y": "1y",
    "5y": "max",
    "max": "max",
}

CONDITION_DISPLAY = {
    "ALL_TIME_HIGH": "All-Time High",
    "BEAR_MARKET": "Bear Market",
    "NEUTRAL_MARKET": "Neutral Market",
}


def _sample_market_data(market_data: list, max_points: int = 10) -> list:
    """Sample market_data down to at most max_points, always including first and last."""
    if len(market_data) <= max_points:
        return market_data
    # Always include first and last; sample remaining evenly
    indices = set()
    indices.add(0)
    indices.add(len(market_data) - 1)
    step = (len(market_data) - 1) / (max_points - 1)
    for i in range(max_points):
        indices.add(min(int(round(i * step)), len(market_data) - 1))
    return [market_data[i] for i in sorted(indices)]


def create_benchmark_comparison_tool(client: GhostfolioClient):
    @tool
    @ttl_cache(ttl=300)
    async def benchmark_comparison(benchmark: str = "SPY", period: str = "ytd") -> str:
        """Compare your portfolio performance against a market benchmark like the S&P 500. Shows market context (trends, conditions) and calculates alpha. Use when user asks 'am I beating the market?', 'compare to S&P', 'portfolio vs benchmark', or 'how is the market doing?'. Do NOT also call portfolio_performance — this tool already includes portfolio return data."""
        period_lower = period.lower()
        start_date = PERIOD_TO_START.get(period_lower, PERIOD_TO_START["ytd"])()
        range_value = PERIOD_TO_RANGE.get(period_lower, "ytd")

        # Phase 1: fetch benchmarks list + portfolio performance in parallel
        benchmarks_data, portfolio_data = await asyncio.gather(
            client.get_benchmarks(),
            client.get_portfolio_performance(range_value),
            return_exceptions=True,
        )

        # Handle benchmarks fetch failure
        if isinstance(benchmarks_data, Exception):
            logger.error("benchmark_comparison_benchmarks_failed", error=str(benchmarks_data))
            return "Sorry, I couldn't fetch benchmark data right now. Please try again later."

        benchmarks_list = benchmarks_data.get("benchmarks", [])

        # Find matching benchmark (case-insensitive symbol match)
        symbol_upper = benchmark.upper().strip()
        matched = None
        for b in benchmarks_list:
            if b.get("symbol", "").upper() == symbol_upper:
                matched = b
                break

        if matched is None:
            available = ", ".join(
                f"{b.get('name', b.get('symbol', ''))} ({b.get('symbol', '')})"
                for b in benchmarks_list
            )
            return (
                f"Benchmark '{benchmark}' not available. "
                f"Available benchmarks: {available}"
            )

        # Extract market context from matched benchmark
        data_source = matched.get("dataSource", "YAHOO")
        bm_symbol = matched.get("symbol", benchmark)
        bm_name = matched.get("name", bm_symbol)
        market_condition_raw = matched.get("marketCondition", "")
        market_condition = CONDITION_DISPLAY.get(market_condition_raw, market_condition_raw)
        trend50d = matched.get("trend50d", "N/A")
        trend200d = matched.get("trend200d", "N/A")

        performances = matched.get("performances", {})
        ath_info = performances.get("allTimeHigh", {})
        ath_perf = ath_info.get("performancePercent")
        if ath_perf is not None:
            ath_distance_str = f"{abs(ath_perf) * 100:.1f}% from ATH"
        else:
            ath_distance_str = "N/A"

        # Phase 2: fetch benchmark detail (safe_fetch — doesn't block on failure)
        detail_data = await safe_fetch(
            client.get_benchmark_detail(data_source, bm_symbol, start_date, range_value),
            label=f"benchmark_detail:{bm_symbol}",
        )

        # Handle portfolio performance result
        portfolio_perf = None
        if not isinstance(portfolio_data, Exception) and portfolio_data is not None:
            perf = portfolio_data.get("performance", {})
            portfolio_return_pct = (perf.get("netPerformancePercentage", 0) or 0) * 100
            portfolio_net_perf = perf.get("netPerformance", 0) or 0
            portfolio_perf = (portfolio_return_pct, portfolio_net_perf)
        else:
            if isinstance(portfolio_data, Exception):
                logger.warning("benchmark_comparison_portfolio_failed", error=str(portfolio_data))

        # Build output
        period_display = period.upper()
        lines = [f"Market & Benchmark Comparison ({period_display})", ""]

        # Market Context section (always shown when benchmark found)
        lines.append("Market Context:")
        lines.append(f"  {bm_name} ({bm_symbol}): {market_condition}, {ath_distance_str}")
        lines.append(f"  50-Day Trend: {trend50d} | 200-Day Trend: {trend200d}")

        # Performance Comparison section (only if detail_data available)
        if detail_data is not None:
            market_data = detail_data.get("marketData", [])
            if market_data:
                benchmark_return = market_data[-1].get("value", 0) or 0
            else:
                benchmark_return = None

            lines.append("")
            lines.append(f"Performance Comparison ({period_display}):")

            if portfolio_perf is not None:
                port_pct, port_net = portfolio_perf
                sign = "+" if port_pct >= 0 else ""
                net_sign = "+" if port_net >= 0 else "-"
                lines.append(
                    f"  Your Portfolio:  {sign}{port_pct:.1f}% "
                    f"({net_sign}${abs(port_net):,.2f})"
                )

            if benchmark_return is not None:
                bm_sign = "+" if benchmark_return >= 0 else ""
                lines.append(f"  {bm_name} ({bm_symbol}):  {bm_sign}{benchmark_return:.1f}%")

            if portfolio_perf is not None and benchmark_return is not None:
                port_pct = portfolio_perf[0]
                alpha = port_pct - benchmark_return
                alpha_sign = "+" if alpha >= 0 else ""
                if abs(alpha) < 0.05:
                    alpha_label = "matching"
                elif alpha > 0:
                    alpha_label = "outperforming"
                else:
                    alpha_label = "underperforming"
                lines.append(f"  Alpha:           {alpha_sign}{alpha:.1f}% ({alpha_label})")

            # Benchmark Timeline section
            if market_data:
                sampled = _sample_market_data(market_data)
                lines.append("")
                lines.append(f"Benchmark Timeline (sampled):")
                for point in sampled:
                    pt_date = point.get("date", "")
                    pt_val = point.get("value", 0) or 0
                    pt_sign = "+" if pt_val >= 0 else ""
                    lines.append(f"  {pt_date}:  {bm_symbol} {pt_sign}{pt_val:.1f}%")
        else:
            # benchmark detail failed — show portfolio line if available but no comparison
            if portfolio_perf is not None:
                port_pct, port_net = portfolio_perf
                lines.append("")
                lines.append(f"Performance Comparison ({period_display}):")
                sign = "+" if port_pct >= 0 else ""
                net_sign = "+" if port_net >= 0 else "-"
                lines.append(
                    f"  Your Portfolio:  {sign}{port_pct:.1f}% "
                    f"({net_sign}${abs(port_net):,.2f})"
                )
                lines.append(
                    f"  Benchmark detail unavailable for {bm_symbol}."
                )

        lines.append("")
        lines.append("[DATA_SOURCES: Ghostfolio]")

        return "\n".join(lines)

    return benchmark_comparison
