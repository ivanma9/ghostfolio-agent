"""Test that verification pipeline is skipped for no-tool (greeting) queries."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from ghostfolio_agent.models.api import ChatRequest


@pytest.fixture
def chat_request():
    return ChatRequest(message="Hello!", session_id="test-session")


@pytest.fixture
def mock_agent():
    """Mock agent that returns a greeting with no tool calls."""
    agent = AsyncMock()
    agent.ainvoke = AsyncMock(return_value={
        "messages": [
            HumanMessage(content="Hello!"),
            AIMessage(content="Hi there! How can I help you today?"),
        ]
    })
    return agent


# Default user returned when auth is disabled
_DEFAULT_USER = {"id": "default", "role": "admin"}


async def test_skip_verification_for_no_tool_queries(chat_request, mock_agent):
    """When agent uses no tools, verification pipeline should not run."""
    with (
        patch("ghostfolio_agent.api.chat._require_user", return_value=_DEFAULT_USER),
        patch("ghostfolio_agent.api.chat._get_user_client", return_value=AsyncMock()),
        patch("ghostfolio_agent.api.chat._create_agent_for_request", return_value=mock_agent),
        patch("ghostfolio_agent.api.chat._get_alert_engine") as mock_alert,
        patch("ghostfolio_agent.api.chat.run_verification_pipeline") as mock_verify,
    ):
        mock_alert.return_value.check_alerts = AsyncMock(return_value=[])

        from ghostfolio_agent.api.chat import chat
        response = await chat(chat_request, user=_DEFAULT_USER)

        mock_verify.assert_not_called()
        assert response.confidence == "high"
        assert response.response == "Hi there! How can I help you today?"


async def test_runs_verification_when_tools_used(chat_request, mock_agent):
    """When agent uses tools, verification pipeline should run."""
    from langchain_core.messages import ToolMessage
    from ghostfolio_agent.verification.pipeline import PipelineResult

    mock_agent.ainvoke = AsyncMock(return_value={
        "messages": [
            HumanMessage(content="What's my portfolio?"),
            AIMessage(content="", additional_kwargs={"tool_calls": [{"id": "1", "function": {"name": "portfolio_summary"}}]}),
            ToolMessage(content="Portfolio value: $10,000", name="portfolio_summary", tool_call_id="1"),
            AIMessage(content="Your portfolio is worth $10,000."),
        ]
    })

    mock_pipeline_result = PipelineResult(
        overall_confidence="high",
        response_text="Your portfolio is worth $10,000.",
    )

    mock_client = AsyncMock()

    with (
        patch("ghostfolio_agent.api.chat._require_user", return_value=_DEFAULT_USER),
        patch("ghostfolio_agent.api.chat._get_user_client", return_value=mock_client),
        patch("ghostfolio_agent.api.chat._create_agent_for_request", return_value=mock_agent),
        patch("ghostfolio_agent.api.chat._get_alert_engine") as mock_alert,
        patch("ghostfolio_agent.api.chat.run_verification_pipeline", return_value=mock_pipeline_result) as mock_verify,
        patch("ghostfolio_agent.api.chat._get_client") as mock_get_client,
    ):
        mock_alert.return_value.check_alerts = AsyncMock(return_value=[])

        from ghostfolio_agent.api.chat import chat
        response = await chat(chat_request, user=_DEFAULT_USER)

        mock_verify.assert_called_once()
        assert response.confidence == "high"
