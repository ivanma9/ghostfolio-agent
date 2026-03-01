from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient
from ghostfolio_agent.tools import create_tools

SYSTEM_PROMPT = """You are a helpful financial assistant for Ghostfolio, a portfolio tracking application. You help users understand their investment portfolio, transactions, and market data.

Guidelines:
- Be selective with tool calls. Only call the tools that directly answer the user's question.
  - For price queries (e.g., "how much is AAPL?", "what's the price of X?", "KO price"): use stock_quote ONLY. Do NOT also call symbol_lookup or portfolio_summary.
  - For general info about a symbol (e.g., "tell me about NVDA"): use symbol_lookup only.
  - For portfolio questions (e.g., "how is my portfolio doing?"): use portfolio_summary or portfolio_performance.
  - For questions that combine both (e.g., "should I buy more AAPL?"): use symbol_lookup + portfolio_summary.
  - Do NOT call portfolio_summary or transaction_history unless the user is explicitly asking about their own holdings or trades.
  - Use the MINIMUM number of tools needed. Do not call extra tools "just in case".
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
- holding_detail: Deep dive into a specific holding — cost basis, P&L, plus earnings dates, analyst consensus, congressional trades, insider activity, and news sentiment
- stock_quote: Get current stock price, day range, open/close, and change. Use when user asks "what's the price of X?" or wants to check a price before trading.
- conviction_score: Get a 0-100 conviction score for any stock symbol — combines analyst consensus, price target upside, news sentiment, and earnings proximity into one composite signal with full breakdown. Use when the user asks about signal strength, conviction, or is evaluating a trade decision.
- morning_briefing: Get a daily morning briefing — portfolio overview, top movers, upcoming earnings, market signals, macro snapshot, and action items. Use when the user asks for a morning briefing, daily update, or wants to know what's happening today.
- activity_log: Record real portfolio activities (buy, sell, dividend) in Ghostfolio

For recording real trades, use activity_log. Always confirm details with the user before recording.

ALERTS: Messages may be prefixed with "ALERTS:" containing proactive notifications about the user's portfolio. These are informational — briefly mention them in your response but do NOT call extra tools to investigate them. Only use tools to answer the user's actual question.
"""

# OpenRouter model catalog
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
    # OpenAI direct (bypasses OpenRouter — cheap for evals)
    {"id": "gpt-4o-mini-direct", "name": "GPT-4o Mini (Direct)", "provider": "OpenAI Direct"},
]

DEFAULT_MODEL = "gpt-4o-mini-direct"

# Models that go direct to provider instead of through OpenRouter
OPENAI_DIRECT_MODELS = {"gpt-4o-mini-direct": "gpt-4o-mini"}


def _summarize_old_messages(messages: list) -> str:
    """Build a deterministic summary of older conversation messages."""
    user_topics: list[str] = []
    tools_used: set[str] = set()
    key_responses: list[str] = []

    for msg in messages:
        if isinstance(msg, HumanMessage):
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            # Strip paper-trading prefix noise
            if "User message:" in text:
                text = text.split("User message:")[-1].strip()
            user_topics.append(text[:150])
        elif isinstance(msg, ToolMessage) and msg.name:
            tools_used.add(msg.name)
        elif isinstance(msg, AIMessage) and msg.content and isinstance(msg.content, str):
            # Keep a brief snippet of each AI response for continuity
            key_responses.append(msg.content[:200])

    parts = ["[Summary of earlier conversation]"]
    if user_topics:
        parts.append("User asked about:")
        for i, topic in enumerate(user_topics, 1):
            parts.append(f"  {i}. {topic}")
    if tools_used:
        parts.append(f"Tools used: {', '.join(sorted(tools_used))}")
    if key_responses:
        parts.append("Key points from your earlier responses:")
        for snippet in key_responses[-3:]:  # last 3 AI responses from the old window
            parts.append(f"  - {snippet}")

    return "\n".join(parts)


def _compact_tool_message(msg: ToolMessage, max_chars: int = 300) -> ToolMessage:
    """Truncate a tool message's content to save tokens."""
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    if len(content) <= max_chars:
        return msg
    truncated = content[:max_chars] + f"... [truncated, was {len(content)} chars]"
    return ToolMessage(
        content=truncated,
        tool_call_id=msg.tool_call_id,
        name=msg.name,
    )


def _make_context_trimmer(max_messages: int = 40):
    """Create a pre_model_hook that compacts old messages and trims to fit context."""

    def trim_context(state):
        messages = state["messages"]

        if len(messages) <= max_messages:
            return {"llm_input_messages": messages}

        # Separate system message
        system_msg = None
        conversation = messages
        if messages and isinstance(messages[0], SystemMessage):
            system_msg = messages[0]
            conversation = messages[1:]

        # Reserve slots: 1 for system, 1 for summary
        keep_count = max_messages - (1 if system_msg else 0) - 1
        old = conversation[:-keep_count]
        recent = conversation[-keep_count:]

        # Don't start on an orphaned ToolMessage (needs preceding AIMessage)
        while recent and hasattr(recent[0], "tool_call_id"):
            recent = recent[1:]

        # Compact tool results in the recent window to save tokens
        recent = [
            _compact_tool_message(m) if isinstance(m, ToolMessage) else m
            for m in recent
        ]

        # Build summary of old messages
        summary = _summarize_old_messages(old)

        result = []
        if system_msg:
            result.append(system_msg)
        result.append(SystemMessage(content=summary))
        result.extend(recent)
        return {"llm_input_messages": result}

    return trim_context


def create_agent(
    client: GhostfolioClient,
    openrouter_api_key: str = "",
    openai_api_key: str = "",
    model_name: str = DEFAULT_MODEL,
    checkpointer=None,
    max_context_messages: int = 40,
    finnhub: FinnhubClient | None = None,
    alpha_vantage: AlphaVantageClient | None = None,
    fmp: FMPClient | None = None,
):
    """Create a LangGraph agent with Ghostfolio tools."""
    if model_name in OPENAI_DIRECT_MODELS:
        llm = ChatOpenAI(
            model=OPENAI_DIRECT_MODELS[model_name],
            api_key=openai_api_key,
            temperature=0,
            max_tokens=4096,
            request_timeout=60,
        )
    else:
        llm = ChatOpenAI(
            model=model_name,
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
            max_tokens=4096,
            request_timeout=60,
        )

    tools = create_tools(client, finnhub=finnhub, alpha_vantage=alpha_vantage, fmp=fmp)
    agent = create_react_agent(
        llm,
        tools,
        prompt=SYSTEM_PROMPT,
        pre_model_hook=_make_context_trimmer(max_context_messages),
        checkpointer=checkpointer,
    )
    return agent
