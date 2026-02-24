from fastapi import APIRouter
from ghostfolio_agent.models.api import ChatRequest, ChatResponse
from ghostfolio_agent.agent.graph import create_agent
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.config import get_settings
from ghostfolio_agent.verification.numerical import verify_numerical_accuracy
from langchain_core.messages import HumanMessage, AIMessage

router = APIRouter()

# In-memory conversation store (session_id -> list of messages)
_conversations: dict[str, list] = {}

# Lazy-initialized agent and module-level client (shared with verifier)
_agent = None
_client: GhostfolioClient | None = None


def _get_agent():
    global _agent, _client
    if _agent is None:
        settings = get_settings()
        _client = GhostfolioClient(
            base_url=settings.ghostfolio_base_url,
            access_token=settings.ghostfolio_access_token,
        )
        _agent = create_agent(_client, api_key=settings.anthropic_api_key)
    return _agent


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    agent = _get_agent()

    # Get or create conversation history
    if request.session_id not in _conversations:
        _conversations[request.session_id] = []

    history = _conversations[request.session_id]

    # Add user message
    history.append(HumanMessage(content=request.message))

    # Run agent
    result = await agent.ainvoke({"messages": history})

    # Extract response and tool calls
    response_messages = result.get("messages", [])

    # Find the last AI message as the response
    ai_response = ""
    tool_calls_made = []
    for msg in response_messages:
        if isinstance(msg, AIMessage) and msg.content and isinstance(msg.content, str):
            ai_response = msg.content
        # Track tool calls
        if hasattr(msg, "name") and msg.name:  # ToolMessage
            tool_calls_made.append(msg.name)

    # Update conversation history with full response
    _conversations[request.session_id] = response_messages

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
    )
