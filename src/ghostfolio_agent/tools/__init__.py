from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.tools.portfolio_summary import create_portfolio_summary_tool
from ghostfolio_agent.tools.transaction_history import create_transaction_history_tool
from ghostfolio_agent.tools.symbol_lookup import create_symbol_lookup_tool
from ghostfolio_agent.tools.portfolio_performance import create_portfolio_performance_tool
from ghostfolio_agent.tools.risk_analysis import create_risk_analysis_tool
from ghostfolio_agent.tools.paper_trade import create_paper_trade_tool


def create_tools(client: GhostfolioClient) -> list:
    """Create all agent tools with the given Ghostfolio client."""
    return [
        create_portfolio_summary_tool(client),
        create_transaction_history_tool(client),
        create_symbol_lookup_tool(client),
        create_portfolio_performance_tool(client),
        create_risk_analysis_tool(client),
        create_paper_trade_tool(client),
    ]
