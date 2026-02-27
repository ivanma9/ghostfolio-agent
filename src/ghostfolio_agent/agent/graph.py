from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.tools import create_tools

SYSTEM_PROMPT = """You are a helpful financial assistant for Ghostfolio, a portfolio tracking application. You help users understand their investment portfolio, transactions, and market data.

Guidelines:
- Be selective with tool calls. Only call the tools that directly answer the user's question.
  - For general info about a symbol (e.g., "tell me about NVDA"): use symbol_lookup only.
  - For portfolio questions (e.g., "how is my portfolio doing?"): use portfolio_summary or portfolio_performance.
  - For questions that combine both (e.g., "should I buy more AAPL?"): use symbol_lookup + portfolio_summary.
  - Do NOT call portfolio_summary or transaction_history unless the user is asking about their own holdings or trades.
- Present financial data clearly with proper formatting (dollar amounts, percentages).
- If you're unsure about something, say so rather than guessing.
- Never provide specific investment advice or recommendations to buy/sell securities.
- Include a brief disclaimer when discussing portfolio performance or financial topics.
- When presenting numbers, round to 2 decimal places for dollar amounts and 1 decimal place for percentages.

Available tools:
- portfolio_summary: Get current holdings, values, and allocations
- transaction_history: Get buy/sell/dividend activity, optionally filtered by symbol
- symbol_lookup: Search for stocks, ETFs, or crypto by name or ticker
- portfolio_performance: Get returns over time (1d, 1w, 1m, 3m, 6m, 1y, ytd, all)
- risk_analysis: Analyze concentration risk, sector breakdown, and currency exposure
- paper_trade: Simulate trades with virtual $100K — buy, sell, view paper portfolio. Supports 'buy 10 AAPL' or 'buy $300 AAPL'. Fetches prices automatically.
- holding_detail: Deep dive into a specific holding — cost basis, P&L, performance
- activity_log: Record real portfolio activities (buy, sell, dividend) in Ghostfolio

For recording real trades, use activity_log. Always confirm details with the user before recording.
"""

# OpenRouter model catalog — id is what OpenRouter expects
AVAILABLE_MODELS = [
    {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "provider": "Anthropic"},
    {"id": "anthropic/claude-haiku-4", "name": "Claude Haiku 4", "provider": "Anthropic"},
    {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI"},
    {"id": "openai/o3-mini", "name": "o3-mini", "provider": "OpenAI"},
    {"id": "google/gemini-2.5-pro-preview", "name": "Gemini 2.5 Pro", "provider": "Google"},
    {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "provider": "Google"},
    {"id": "deepseek/deepseek-chat-v3-0324", "name": "DeepSeek V3", "provider": "DeepSeek"},
    {"id": "meta-llama/llama-4-maverick", "name": "Llama 4 Maverick", "provider": "Meta"},
]

DEFAULT_MODEL = "anthropic/claude-sonnet-4"


def _make_context_trimmer(max_messages: int = 40):
    """Create a pre_model_hook that trims messages to fit context window."""

    def trim_context(state):
        messages = state["messages"]

        if len(messages) <= max_messages:
            return {"llm_input_messages": messages}

        # Keep the system message (if first) + last N messages
        trimmed = []
        if messages and isinstance(messages[0], SystemMessage):
            trimmed.append(messages[0])
            candidates = messages[1:]
        else:
            candidates = messages

        tail = candidates[-(max_messages - len(trimmed)) :]

        # Don't start on an orphaned ToolMessage (needs preceding AIMessage)
        while tail and hasattr(tail[0], "tool_call_id"):
            tail = tail[1:]

        trimmed.extend(tail)
        return {"llm_input_messages": trimmed}

    return trim_context


def create_agent(
    client: GhostfolioClient,
    api_key: str,
    model_name: str = DEFAULT_MODEL,
    checkpointer=None,
    max_context_messages: int = 40,
):
    """Create a LangGraph agent with Ghostfolio tools, using OpenRouter."""
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
        max_tokens=4096,
    )
    tools = create_tools(client)
    agent = create_react_agent(
        llm,
        tools,
        prompt=SYSTEM_PROMPT,
        pre_model_hook=_make_context_trimmer(max_context_messages),
        checkpointer=checkpointer,
    )
    return agent
