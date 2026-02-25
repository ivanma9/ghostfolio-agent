import structlog
from fastapi import APIRouter
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from ghostfolio_agent.models.api import Citation, ChatRequest, ChatResponse

logger = structlog.get_logger()
from ghostfolio_agent.agent.graph import create_agent
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.config import get_settings
from ghostfolio_agent.verification.numerical import verify_numerical_accuracy

router = APIRouter()

# Lazy-initialized agent and shared client
_agent = None
_client: GhostfolioClient | None = None
_checkpointer: InMemorySaver | None = None


def _get_agent():
    global _agent, _client, _checkpointer
    if _agent is None:
        settings = get_settings()
        _client = GhostfolioClient(
            base_url=settings.ghostfolio_base_url,
            access_token=settings.ghostfolio_access_token,
        )
        # InMemorySaver keeps state across invocations within the process.
        # Swap to SqliteSaver or PostgresSaver for cross-restart persistence.
        _checkpointer = InMemorySaver()
        _agent = create_agent(
            _client,
            api_key=settings.anthropic_api_key,
            checkpointer=_checkpointer,
            max_context_messages=settings.max_context_messages,
        )
    return _agent


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


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        agent = _get_agent()

        # Checkpointer manages history per thread_id — only send the new message
        config = {"configurable": {"thread_id": request.session_id}}
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
        )

        # Extract response and tool calls from messages
        response_messages = result.get("messages", [])
        ai_response = ""
        tool_calls_made = []
        for msg in response_messages:
            if isinstance(msg, AIMessage) and msg.content and isinstance(msg.content, str):
                ai_response = msg.content
            if isinstance(msg, ToolMessage) and msg.name:
                tool_calls_made.append(msg.name)

        # Build citations from tool call results
        citations = _extract_citations(response_messages)

        # Run numerical verification against live Ghostfolio data
        confidence = "high"
        if _client is not None and ai_response:
            verification = await verify_numerical_accuracy(ai_response, _client)
            confidence = verification.confidence

        return ChatResponse(
            response=ai_response,
            session_id=request.session_id,
            tool_calls=list(set(tool_calls_made)),
            confidence=confidence,
            citations=citations,
        )
    except Exception as e:
        logger.error("chat_endpoint_failed", error=str(e), session_id=request.session_id)
        return ChatResponse(
            response="Sorry, something went wrong processing your request. Please try again.",
            session_id=request.session_id,
            tool_calls=[],
            confidence="low",
            citations=[],
        )
