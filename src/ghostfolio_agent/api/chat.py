import structlog
from fastapi import APIRouter
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from ghostfolio_agent.models.api import Citation, ChatRequest, ChatResponse

logger = structlog.get_logger()
from ghostfolio_agent.agent.graph import create_agent, AVAILABLE_MODELS, DEFAULT_MODEL
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.config import get_settings
from ghostfolio_agent.verification.numerical import verify_numerical_accuracy

router = APIRouter()

# Shared state
_client: GhostfolioClient | None = None
_checkpointer: InMemorySaver | None = None
_agents: dict[str, object] = {}  # model_name -> agent


def _get_client() -> GhostfolioClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = GhostfolioClient(
            base_url=settings.ghostfolio_base_url,
            access_token=settings.ghostfolio_access_token,
        )
    return _client


def _get_checkpointer() -> InMemorySaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = InMemorySaver()
    return _checkpointer


def _get_agent(model_name: str = DEFAULT_MODEL):
    global _agents
    if model_name not in _agents:
        settings = get_settings()
        _agents[model_name] = create_agent(
            _get_client(),
            api_key=settings.openrouter_api_key,
            model_name=model_name,
            checkpointer=_get_checkpointer(),
            max_context_messages=settings.max_context_messages,
        )
    return _agents[model_name]


def _extract_citations(messages: list) -> list[Citation]:
    """Build citations from tool call/result pairs in the message history."""
    citations = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            # Truncate long tool results for the citation source_detail
            detail = content[:200] + "..." if len(content) > 200 else content
            citations.append(
                Citation(
                    claim=f"Data from {msg.name}",
                    tool_name=msg.name,
                    source_detail=detail,
                )
            )
    return citations


@router.get("/api/models")
async def list_models():
    """Return available models for the frontend selector."""
    return {"models": AVAILABLE_MODELS, "default": DEFAULT_MODEL}


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        model = request.model or DEFAULT_MODEL
        agent = _get_agent(model)

        # Wrap message with paper trading instruction if enabled
        content = request.message
        if request.paper_trading:
            content = (
                f"[PAPER TRADING MODE] The user has paper trading mode enabled. "
                f"For any buy/sell/trade intent, use the paper_trade tool directly. "
                f"The paper_trade tool accepts actions like 'buy 10 AAPL' or 'sell 5 NVDA' — "
                f"it looks up prices automatically, so do NOT look up prices yourself. "
                f"If the user specifies a dollar amount (e.g. '$300 of MU'), calculate the "
                f"number of shares by looking up the price with symbol_lookup first, then "
                f"call paper_trade with the share count. "
                f"User message: {request.message}"
            )

        # Checkpointer manages history per thread_id — only send the new message
        config = {"configurable": {"thread_id": request.session_id}}
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=content)]},
            config=config,
        )

        # Extract response and tool calls from messages
        response_messages = result.get("messages", [])
        ai_response = ""
        tool_calls_made = []
        tool_outputs = []
        for msg in response_messages:
            if isinstance(msg, AIMessage) and msg.content and isinstance(msg.content, str):
                ai_response = msg.content
            if isinstance(msg, ToolMessage) and msg.name:
                tool_calls_made.append(msg.name)
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                tool_outputs.append(content)

        # Build citations from tool call results
        citations = _extract_citations(response_messages)

        # Run numerical verification against live Ghostfolio data
        confidence = "high"
        client = _get_client()
        if client is not None and ai_response:
            verification = await verify_numerical_accuracy(ai_response, client)
            confidence = verification.confidence

        return ChatResponse(
            response=ai_response,
            session_id=request.session_id,
            tool_calls=list(set(tool_calls_made)),
            tool_outputs=tool_outputs,
            confidence=confidence,
            citations=citations,
        )
    except Exception as e:
        logger.error("chat_endpoint_failed", error=str(e), session_id=request.session_id)
        return ChatResponse(
            response="Sorry, something went wrong processing your request. Please try again.",
            session_id=request.session_id,
            tool_calls=[],
            tool_outputs=[],
            confidence="low",
            citations=[],
        )
