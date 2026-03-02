from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient
from ghostfolio_agent.clients.congressional import CongressionalClient
from ghostfolio_agent.tools.portfolio_summary import create_portfolio_summary_tool
from ghostfolio_agent.tools.transaction_history import create_transaction_history_tool
from ghostfolio_agent.tools.symbol_lookup import create_symbol_lookup_tool
from ghostfolio_agent.tools.portfolio_performance import create_portfolio_performance_tool
from ghostfolio_agent.tools.risk_analysis import create_risk_analysis_tool
from ghostfolio_agent.tools.paper_trade import create_paper_trade_tool
from ghostfolio_agent.tools.holding_detail import create_holding_detail_tool
from ghostfolio_agent.tools.activity_log import create_activity_log_tool
from ghostfolio_agent.tools.stock_quote import create_stock_quote_tool
from ghostfolio_agent.tools.conviction_score import create_conviction_score_tool
from ghostfolio_agent.tools.morning_briefing import create_morning_briefing_tool
from ghostfolio_agent.tools.congressional import (
    create_congressional_trades_tool,
    create_congressional_summary_tool,
    create_congressional_members_tool,
)
from ghostfolio_agent.tools.benchmark_comparison import create_benchmark_comparison_tool


def create_tools(
    client: GhostfolioClient | None,
    finnhub: FinnhubClient | None = None,
    alpha_vantage: AlphaVantageClient | None = None,
    fmp: FMPClient | None = None,
    congressional: CongressionalClient | None = None,
    guest: bool = False,
) -> list:
    """Create agent tools. When guest=True, only include guest-safe tools."""
    if guest:
        # Guest mode — only tools that don't require a Ghostfolio portfolio
        tools = []

        if client is not None:
            tools.append(create_paper_trade_tool(client))

        if finnhub is not None:
            tools.append(create_stock_quote_tool(client, finnhub=finnhub))

        if finnhub is not None or alpha_vantage is not None or fmp is not None:
            tools.append(
                create_conviction_score_tool(
                    finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp, congressional=congressional
                )
            )

        if congressional is not None:
            tools.extend([
                create_congressional_trades_tool(congressional),
                create_congressional_summary_tool(congressional),
                create_congressional_members_tool(congressional),
            ])

        return tools

    # Full mode — client is available
    tools = [
        create_portfolio_summary_tool(client),
        create_transaction_history_tool(client),
        create_symbol_lookup_tool(client),
        create_portfolio_performance_tool(client),
        create_risk_analysis_tool(client),
        create_paper_trade_tool(client),
        create_holding_detail_tool(client, finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp, congressional=congressional),
        create_activity_log_tool(client),
        create_stock_quote_tool(client, finnhub=finnhub),
        create_conviction_score_tool(finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp, congressional=congressional),
        create_morning_briefing_tool(client, finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp, congressional=congressional),
        create_benchmark_comparison_tool(client),
    ]

    if congressional is not None:
        tools.extend([
            create_congressional_trades_tool(congressional),
            create_congressional_summary_tool(congressional),
            create_congressional_members_tool(congressional),
        ])

    return tools
