import structlog
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient

logger = structlog.get_logger()

PERIOD_MAP = {
    "1d": "1d",
    "1w": "1w",
    "1m": "1m",
    "3m": "3m",
    "6m": "6m",
    "1y": "1y",
    "ytd": "ytd",
    "all": "max",
    "max": "max",
}


def create_portfolio_performance_tool(client: GhostfolioClient):
    @tool
    async def portfolio_performance(period: str = "1m") -> str:
        """Get portfolio performance over a time period. Supported periods: 1d, 1w, 1m, 3m, 6m, 1y, ytd, all. Use this when the user asks about returns, performance, or how their portfolio has done."""
        range_value = PERIOD_MAP.get(period.lower(), "1m")
        try:
            data = await client.get_portfolio_performance(range_value)
        except Exception as e:
            logger.error("portfolio_performance_failed", error=str(e), period=period)
            return "Sorry, I couldn't fetch your portfolio performance right now. Please try again later."

        perf = data.get("performance", {})
        net_perf = perf.get("netPerformance", 0) or 0
        net_perf_pct = (perf.get("netPerformancePercentage", 0) or 0) * 100
        current_value = perf.get("currentNetWorth", 0) or 0

        chart = data.get("chart", []) or []

        lines = [
            f"Portfolio Performance ({period.upper()}):",
            f"  Period: {period.upper()}",
            f"  Total Return: ${net_perf:,.2f} ({net_perf_pct:+.2f}%)",
            f"  Current Value: ${current_value:,.2f}",
        ]

        if chart:
            lines.append("")
            lines.append("Data Points:")
            if len(chart) > 20:
                step = len(chart) / 20
                sampled = [chart[int(i * step)] for i in range(20)]
                if chart[-1] not in sampled:
                    sampled.append(chart[-1])
            else:
                sampled = chart
            for point in sampled:
                date = point.get("date", "")
                value = point.get("netWorth", 0) or point.get("value", 0) or 0
                lines.append(f"  {date}: ${value:,.2f}")

        return "\n".join(lines)

    return portfolio_performance
