from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient
from ghostfolio_agent.tools.portfolio_summary import create_portfolio_summary_tool
from ghostfolio_agent.tools.transaction_history import create_transaction_history_tool
from ghostfolio_agent.tools.symbol_lookup import create_symbol_lookup_tool
from ghostfolio_agent.tools.portfolio_performance import create_portfolio_performance_tool
from ghostfolio_agent.tools.risk_analysis import create_risk_analysis_tool
from ghostfolio_agent.tools.paper_trade import create_paper_trade_tool


def create_tools(
    client: GhostfolioClient,
    finnhub: FinnhubClient | None = None,
    alpha_vantage: AlphaVantageClient | None = None,
    fmp: FMPClient | None = None,
) -> list:
    """Create all agent tools with the given clients."""
    tools = [
        create_portfolio_summary_tool(client),
        create_transaction_history_tool(client),
        create_symbol_lookup_tool(client),
        create_portfolio_performance_tool(client),
        create_risk_analysis_tool(client),
        create_paper_trade_tool(client),
    ]
    # 3rd party enriched tools will be added here in future tasks
    return tools
