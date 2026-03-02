"""Integration tests for the POST /api/chat endpoint.

Uses httpx.AsyncClient with httpx.ASGITransport to exercise the full FastAPI
request/response cycle without spinning up a real server.  All external
dependencies (LLM agent, clients, checkpointer, alert engine) are replaced
with unittest.mock objects so these tests are hermetic and fast.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ghostfolio_agent.api.chat import router as chat_router
from ghostfolio_agent.models.api import ChatRequest
from ghostfolio_agent.verification.pipeline import PipelineResult

# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------
# Build a minimal FastAPI app that mounts the chat router.  We intentionally
# avoid importing the real `main.py` app because it reads settings + mounts
# static files at module-load time, which isn't needed for these tests.


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router)
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NO_OP_PIPELINE = PipelineResult(
    overall_confidence="high",
    response_text="Mocked response text.",
)

_TOOL_PIPELINE = PipelineResult(
    overall_confidence="high",
    response_text="Your portfolio is worth $10,000.",
)


def _make_agent(messages: list) -> AsyncMock:
    """Return an agent AsyncMock whose ainvoke returns the given message list."""
    agent = AsyncMock()
    agent.ainvoke = AsyncMock(return_value={"messages": messages})
    return agent


def _make_alert_engine(alerts: list[str] | None = None) -> MagicMock:
    """Return a mock AlertEngine that fires the given alerts (or none)."""
    engine = MagicMock()
    engine.check_alerts = AsyncMock(return_value=alerts or [])
    return engine


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app() -> FastAPI:
    return _make_test_app()


@pytest.fixture()
async def client(app: FastAPI):
    """Async httpx client wired to the test app via ASGITransport."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Base patcher — suppresses all real singleton initialisation for every test
# in this module.  Individual tests can override by providing their own patch
# inside the test body.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_singletons():
    """Patch all singleton getters so no real network calls are made."""
    mock_ghostfolio = AsyncMock()
    mock_finnhub = None
    mock_alpha_vantage = None
    mock_fmp = None
    mock_congressional = None
    mock_checkpointer = AsyncMock()

    with (
        patch("ghostfolio_agent.api.chat._get_client", return_value=mock_ghostfolio),
        patch("ghostfolio_agent.api.chat._get_finnhub", return_value=mock_finnhub),
        patch("ghostfolio_agent.api.chat._get_alpha_vantage", return_value=mock_alpha_vantage),
        patch("ghostfolio_agent.api.chat._get_fmp", return_value=mock_fmp),
        patch("ghostfolio_agent.api.chat._get_congressional", return_value=mock_congressional),
        patch("ghostfolio_agent.api.chat._get_checkpointer", return_value=mock_checkpointer),
    ):
        yield


# ---------------------------------------------------------------------------
# 1. No-tool chat — plain greeting
# ---------------------------------------------------------------------------


class TestNoToolChat:
    """Agent responds with no tool calls → high confidence, empty tool_calls."""

    async def test_greeting_returns_200(self, client: httpx.AsyncClient):
        greeting_agent = _make_agent([
            HumanMessage(content="Hello!"),
            AIMessage(content="Hi there! How can I help you today?"),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=greeting_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
        ):
            resp = await client.post("/api/chat", json={"message": "Hello!", "session_id": "s1"})

        assert resp.status_code == 200

    async def test_greeting_confidence_is_high(self, client: httpx.AsyncClient):
        greeting_agent = _make_agent([
            HumanMessage(content="Hello!"),
            AIMessage(content="Hi there! How can I help you today?"),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=greeting_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
        ):
            resp = await client.post("/api/chat", json={"message": "Hello!", "session_id": "s1"})

        body = resp.json()
        assert body["confidence"] == "high"

    async def test_greeting_tool_calls_empty(self, client: httpx.AsyncClient):
        greeting_agent = _make_agent([
            HumanMessage(content="Hello!"),
            AIMessage(content="Hi there! How can I help you today?"),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=greeting_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
        ):
            resp = await client.post("/api/chat", json={"message": "Hello!", "session_id": "s1"})

        body = resp.json()
        assert body["tool_calls"] == []

    async def test_greeting_response_text_preserved(self, client: httpx.AsyncClient):
        greeting_agent = _make_agent([
            HumanMessage(content="Hello!"),
            AIMessage(content="Hi there! How can I help you today?"),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=greeting_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
        ):
            resp = await client.post("/api/chat", json={"message": "Hello!", "session_id": "s1"})

        body = resp.json()
        assert "Hi there" in body["response"]

    async def test_greeting_session_id_echoed(self, client: httpx.AsyncClient):
        greeting_agent = _make_agent([
            HumanMessage(content="Hello!"),
            AIMessage(content="Hi there!"),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=greeting_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
        ):
            resp = await client.post(
                "/api/chat", json={"message": "Hello!", "session_id": "my-session-42"}
            )

        assert resp.json()["session_id"] == "my-session-42"


# ---------------------------------------------------------------------------
# 2. Tool invocation
# ---------------------------------------------------------------------------


class TestToolInvocation:
    """Agent invokes a tool → tool name appears in response.tool_calls."""

    async def test_tool_call_name_in_response(self, client: httpx.AsyncClient):
        tool_agent = _make_agent([
            HumanMessage(content="What's my portfolio?"),
            AIMessage(
                content="",
                additional_kwargs={"tool_calls": [{"id": "tc-1", "function": {"name": "portfolio_summary"}}]},
            ),
            ToolMessage(
                content="Portfolio value: $10,000",
                name="portfolio_summary",
                tool_call_id="tc-1",
            ),
            AIMessage(content="Your portfolio is worth $10,000."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=_TOOL_PIPELINE,
            ),
        ):
            resp = await client.post(
                "/api/chat", json={"message": "What's my portfolio?", "session_id": "s2"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "portfolio_summary" in body["tool_calls"]

    async def test_tool_output_in_response(self, client: httpx.AsyncClient):
        tool_agent = _make_agent([
            HumanMessage(content="What's my portfolio?"),
            AIMessage(content="", additional_kwargs={}),
            ToolMessage(
                content="Portfolio value: $10,000",
                name="portfolio_summary",
                tool_call_id="tc-2",
            ),
            AIMessage(content="Your portfolio is worth $10,000."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=_TOOL_PIPELINE,
            ),
        ):
            resp = await client.post(
                "/api/chat", json={"message": "What's my portfolio?", "session_id": "s2"}
            )

        body = resp.json()
        assert len(body["tool_outputs"]) == 1
        assert "Portfolio value" in body["tool_outputs"][0]

    async def test_citation_created_for_tool(self, client: httpx.AsyncClient):
        tool_agent = _make_agent([
            HumanMessage(content="What's my portfolio?"),
            AIMessage(content=""),
            ToolMessage(
                content="Portfolio value: $10,000",
                name="portfolio_summary",
                tool_call_id="tc-3",
            ),
            AIMessage(content="Your portfolio is worth $10,000."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=_TOOL_PIPELINE,
            ),
        ):
            resp = await client.post(
                "/api/chat", json={"message": "What's my portfolio?", "session_id": "s2"}
            )

        body = resp.json()
        assert len(body["citations"]) == 1
        assert body["citations"][0]["tool_name"] == "portfolio_summary"

    async def test_multiple_tool_calls_deduplicated(self, client: httpx.AsyncClient):
        """tool_calls list deduplicates repeated tool names."""
        tool_agent = _make_agent([
            HumanMessage(content="Summarise and show performance"),
            ToolMessage(content="Holdings: ...", name="portfolio_summary", tool_call_id="tc-a"),
            ToolMessage(content="Returns: ...", name="portfolio_summary", tool_call_id="tc-b"),
            ToolMessage(content="Perf: ...", name="portfolio_performance", tool_call_id="tc-c"),
            AIMessage(content="Here is your portfolio overview."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=_TOOL_PIPELINE,
            ),
        ):
            resp = await client.post(
                "/api/chat",
                json={"message": "Summarise and show performance", "session_id": "s3"},
            )

        body = resp.json()
        # tool_calls is a set converted to list — each tool name should appear once
        assert body["tool_calls"].count("portfolio_summary") == 1
        assert "portfolio_performance" in body["tool_calls"]


# ---------------------------------------------------------------------------
# 3. Alert fires — alert text injected into agent invocation
# ---------------------------------------------------------------------------


class TestAlertFires:
    """When the alert engine returns alerts they are prepended to the message
    that the agent receives."""

    async def test_alert_text_reaches_agent(self, client: httpx.AsyncClient):
        captured_invocations: list[dict] = []

        async def _fake_ainvoke(payload: dict, config: dict):
            captured_invocations.append(payload)
            return {
                "messages": [
                    HumanMessage(content=payload["messages"][0].content),
                    AIMessage(content="You have an alert."),
                ]
            }

        agent = AsyncMock()
        agent.ainvoke = _fake_ainvoke

        alert_engine = _make_alert_engine(["AAPL earnings in 2 days"])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=alert_engine),
        ):
            resp = await client.post(
                "/api/chat", json={"message": "What should I do?", "session_id": "s4"}
            )

        assert resp.status_code == 200
        # Inspect what the agent actually received
        assert len(captured_invocations) == 1
        injected_content = captured_invocations[0]["messages"][0].content
        assert "ALERTS:" in injected_content
        assert "AAPL earnings in 2 days" in injected_content
        assert "What should I do?" in injected_content

    async def test_multiple_alerts_all_injected(self, client: httpx.AsyncClient):
        captured: list[str] = []

        async def _fake_ainvoke(payload: dict, config: dict):
            captured.append(payload["messages"][0].content)
            return {
                "messages": [
                    HumanMessage(content="hi"),
                    AIMessage(content="Noted."),
                ]
            }

        agent = AsyncMock()
        agent.ainvoke = _fake_ainvoke

        alerts = ["AAPL earnings in 2 days", "NVDA big mover +6.2%", "TSLA congressional sell"]
        alert_engine = _make_alert_engine(alerts)

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=alert_engine),
        ):
            await client.post("/api/chat", json={"message": "hi", "session_id": "s5"})

        for alert_text in alerts:
            assert alert_text in captured[0]

    async def test_no_alerts_no_prefix(self, client: httpx.AsyncClient):
        captured: list[str] = []

        async def _fake_ainvoke(payload: dict, config: dict):
            captured.append(payload["messages"][0].content)
            return {
                "messages": [
                    HumanMessage(content="hi"),
                    AIMessage(content="Hello!"),
                ]
            }

        agent = AsyncMock()
        agent.ainvoke = _fake_ainvoke

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine([])),
        ):
            await client.post("/api/chat", json={"message": "hi", "session_id": "s6"})

        assert "ALERTS:" not in captured[0]
        assert captured[0] == "hi"

    async def test_alert_engine_failure_does_not_break_chat(self, client: httpx.AsyncClient):
        """If the alert engine raises, the endpoint should continue without alerts."""
        agent = _make_agent([
            HumanMessage(content="hi"),
            AIMessage(content="Hello!"),
        ])

        failing_engine = MagicMock()
        failing_engine.check_alerts = AsyncMock(side_effect=RuntimeError("network down"))

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=failing_engine),
        ):
            resp = await client.post("/api/chat", json={"message": "hi", "session_id": "s7"})

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. Data source extraction
# ---------------------------------------------------------------------------


class TestDataSourceExtraction:
    """Tool output containing [DATA_SOURCES: ...] → response.data_sources populated."""

    async def test_single_source_extracted(self, client: httpx.AsyncClient):
        tool_agent = _make_agent([
            HumanMessage(content="What's AAPL?"),
            ToolMessage(
                content="AAPL — Apple Inc.\n  Price: $150.00\n[DATA_SOURCES: Finnhub]",
                name="stock_quote",
                tool_call_id="tc-ds1",
            ),
            AIMessage(content="AAPL is trading at $150."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=PipelineResult(overall_confidence="high", response_text="AAPL is $150."),
            ),
        ):
            resp = await client.post(
                "/api/chat", json={"message": "What's AAPL?", "session_id": "s8"}
            )

        body = resp.json()
        assert "Finnhub" in body["data_sources"]

    async def test_multiple_sources_extracted_and_sorted(self, client: httpx.AsyncClient):
        tool_agent = _make_agent([
            HumanMessage(content="Analyse AAPL"),
            ToolMessage(
                content="Conviction: 72/100\n[DATA_SOURCES: Finnhub, Alpha Vantage, FMP]",
                name="conviction_score",
                tool_call_id="tc-ds2",
            ),
            AIMessage(content="Conviction is 72."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=PipelineResult(overall_confidence="high", response_text="Conviction 72."),
            ),
        ):
            resp = await client.post(
                "/api/chat", json={"message": "Analyse AAPL", "session_id": "s9"}
            )

        body = resp.json()
        assert sorted(body["data_sources"]) == ["Alpha Vantage", "FMP", "Finnhub"]

    async def test_data_sources_line_stripped_from_tool_output(self, client: httpx.AsyncClient):
        """The [DATA_SOURCES: ...] metadata line must not appear in tool_outputs."""
        raw_output = "AAPL — Apple Inc.\n  Price: $150.00\n[DATA_SOURCES: Finnhub]"
        tool_agent = _make_agent([
            HumanMessage(content="Price?"),
            ToolMessage(content=raw_output, name="stock_quote", tool_call_id="tc-ds3"),
            AIMessage(content="$150."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=PipelineResult(overall_confidence="high", response_text="$150."),
            ),
        ):
            resp = await client.post("/api/chat", json={"message": "Price?", "session_id": "s10"})

        body = resp.json()
        for output in body["tool_outputs"]:
            assert "[DATA_SOURCES:" not in output

    async def test_no_data_sources_returns_empty_list(self, client: httpx.AsyncClient):
        tool_agent = _make_agent([
            HumanMessage(content="hi"),
            ToolMessage(content="Plain output with no metadata.", name="portfolio_summary", tool_call_id="tc-ds4"),
            AIMessage(content="Done."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=PipelineResult(overall_confidence="high", response_text="Done."),
            ),
        ):
            resp = await client.post("/api/chat", json={"message": "hi", "session_id": "s11"})

        assert resp.json()["data_sources"] == []

    async def test_deduplication_across_tool_outputs(self, client: httpx.AsyncClient):
        """Sources mentioned in multiple tool outputs are deduplicated."""
        tool_agent = _make_agent([
            HumanMessage(content="multi"),
            ToolMessage(content="A\n[DATA_SOURCES: Finnhub]", name="stock_quote", tool_call_id="tc-a"),
            ToolMessage(content="B\n[DATA_SOURCES: Finnhub, FMP]", name="holding_detail", tool_call_id="tc-b"),
            AIMessage(content="Done."),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch(
                "ghostfolio_agent.api.chat.run_verification_pipeline",
                return_value=PipelineResult(overall_confidence="high", response_text="Done."),
            ),
        ):
            resp = await client.post("/api/chat", json={"message": "multi", "session_id": "s12"})

        body = resp.json()
        assert body["data_sources"].count("Finnhub") == 1


# ---------------------------------------------------------------------------
# 5. Session persistence — same session_id across two requests
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    """Two messages with the same session_id should both succeed."""

    async def test_two_messages_same_session_both_200(self, client: httpx.AsyncClient):
        def _agent_factory():
            """Returns a fresh agent mock each call (simulates _get_agent caching)."""
            return _make_agent([
                HumanMessage(content="msg"),
                AIMessage(content="Reply."),
            ])

        alert_engine = _make_alert_engine()

        with (
            patch("ghostfolio_agent.api.chat._get_agent", side_effect=lambda m=None: _agent_factory()),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=alert_engine),
        ):
            resp1 = await client.post(
                "/api/chat", json={"message": "First message", "session_id": "persistent-session"}
            )
            resp2 = await client.post(
                "/api/chat", json={"message": "Second message", "session_id": "persistent-session"}
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200

    async def test_different_sessions_independent(self, client: httpx.AsyncClient):
        """Different session_ids do not interfere."""

        def _agent_factory(model=None):
            return _make_agent([
                HumanMessage(content="msg"),
                AIMessage(content="Reply."),
            ])

        alert_engine = _make_alert_engine()

        with (
            patch("ghostfolio_agent.api.chat._get_agent", side_effect=_agent_factory),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=alert_engine),
        ):
            resp_a = await client.post(
                "/api/chat", json={"message": "Hello", "session_id": "session-A"}
            )
            resp_b = await client.post(
                "/api/chat", json={"message": "Hello", "session_id": "session-B"}
            )

        assert resp_a.json()["session_id"] == "session-A"
        assert resp_b.json()["session_id"] == "session-B"

    async def test_session_id_default_is_accepted(self, client: httpx.AsyncClient):
        """Omitting session_id uses the default value ('default') without error."""
        agent = _make_agent([
            HumanMessage(content="hi"),
            AIMessage(content="Hello!"),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
        ):
            # POST without session_id key — model default kicks in
            resp = await client.post("/api/chat", json={"message": "hi"})

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "default"


# ---------------------------------------------------------------------------
# 6. Timeout — agent raises TimeoutError
# ---------------------------------------------------------------------------


class TestTimeout:
    """When the agent times out the endpoint returns a graceful timeout message."""

    async def test_timeout_returns_200(self, client: httpx.AsyncClient):
        async def _slow_ainvoke(payload, config):
            raise TimeoutError("too slow")

        agent = AsyncMock()
        agent.ainvoke = _slow_ainvoke

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            # Patch asyncio.timeout so the TimeoutError is raised immediately
            patch("ghostfolio_agent.api.chat.asyncio.timeout") as mock_timeout,
        ):
            # Make asyncio.timeout a no-op context manager so our TimeoutError propagates
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=None)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_timeout.return_value = mock_ctx

            resp = await client.post(
                "/api/chat", json={"message": "Give me everything", "session_id": "s-timeout"}
            )

        assert resp.status_code == 200

    async def test_timeout_response_confidence_is_low(self, client: httpx.AsyncClient):
        async def _slow_ainvoke(payload, config):
            raise TimeoutError("too slow")

        agent = AsyncMock()
        agent.ainvoke = _slow_ainvoke

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch("ghostfolio_agent.api.chat.asyncio.timeout") as mock_timeout,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=None)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_timeout.return_value = mock_ctx

            resp = await client.post(
                "/api/chat", json={"message": "Give me everything", "session_id": "s-timeout"}
            )

        body = resp.json()
        assert body["confidence"] == "low"

    async def test_timeout_message_content(self, client: httpx.AsyncClient):
        async def _slow_ainvoke(payload, config):
            raise TimeoutError("too slow")

        agent = AsyncMock()
        agent.ainvoke = _slow_ainvoke

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch("ghostfolio_agent.api.chat.asyncio.timeout") as mock_timeout,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=None)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_timeout.return_value = mock_ctx

            resp = await client.post(
                "/api/chat", json={"message": "Give me everything", "session_id": "s-timeout"}
            )

        body = resp.json()
        # The endpoint has a specific timeout message
        assert "took too long" in body["response"] or "try again" in body["response"].lower()

    async def test_timeout_tool_calls_empty(self, client: httpx.AsyncClient):
        async def _slow_ainvoke(payload, config):
            raise TimeoutError()

        agent = AsyncMock()
        agent.ainvoke = _slow_ainvoke

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch("ghostfolio_agent.api.chat.asyncio.timeout") as mock_timeout,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=None)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_timeout.return_value = mock_ctx

            resp = await client.post(
                "/api/chat", json={"message": "slow query", "session_id": "s-timeout2"}
            )

        body = resp.json()
        assert body["tool_calls"] == []
        assert body["data_sources"] == []


# ---------------------------------------------------------------------------
# 7. Additional edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Miscellaneous edge-case coverage."""

    async def test_paper_trading_mode_prefixes_message(self, client: httpx.AsyncClient):
        """paper_trading=True → agent receives PAPER TRADING MODE prefix."""
        captured: list[str] = []

        async def _fake_ainvoke(payload: dict, config: dict):
            captured.append(payload["messages"][0].content)
            return {
                "messages": [
                    HumanMessage(content="buy 10 AAPL"),
                    AIMessage(content="Executed paper trade."),
                ]
            }

        agent = AsyncMock()
        agent.ainvoke = _fake_ainvoke

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
        ):
            resp = await client.post(
                "/api/chat",
                json={"message": "buy 10 AAPL", "session_id": "s-paper", "paper_trading": True},
            )

        assert resp.status_code == 200
        assert "PAPER TRADING MODE ACTIVE" in captured[0]
        assert "buy 10 AAPL" in captured[0]

    async def test_graph_interrupt_returns_confirmation_prompt(self, client: httpx.AsyncClient):
        """GraphInterrupt mid-graph → 200 with the interrupt prompt as response."""
        from langgraph.errors import GraphInterrupt

        async def _interrupt_ainvoke(payload: dict, config: dict):
            raise GraphInterrupt("Please confirm: buy 10 AAPL at $150 each — proceed?")

        agent = AsyncMock()
        agent.ainvoke = _interrupt_ainvoke

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch("ghostfolio_agent.api.chat.asyncio.timeout") as mock_timeout,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=None)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_timeout.return_value = mock_ctx

            resp = await client.post(
                "/api/chat",
                json={"message": "buy 10 AAPL", "session_id": "s-interrupt"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "confirm" in body["response"].lower()
        assert body["confidence"] == "high"

    async def test_response_model_fields_present(self, client: httpx.AsyncClient):
        """All ChatResponse fields must be present in the JSON response."""
        agent = _make_agent([
            HumanMessage(content="hi"),
            AIMessage(content="Hello!"),
        ])

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
        ):
            resp = await client.post("/api/chat", json={"message": "hi", "session_id": "s-fields"})

        body = resp.json()
        expected_fields = {
            "response", "session_id", "tool_calls", "tool_outputs",
            "confidence", "citations", "verification_issues",
            "verification_details", "data_sources",
        }
        assert expected_fields.issubset(body.keys())

    async def test_invalid_request_body_returns_422(self, client: httpx.AsyncClient):
        """Missing required 'message' field → 422 Unprocessable Entity."""
        resp = await client.post("/api/chat", json={"session_id": "s-bad"})
        assert resp.status_code == 422

    async def test_verification_pipeline_called_with_tool_output(self, client: httpx.AsyncClient):
        """run_verification_pipeline is called exactly once when tools are used."""
        from unittest.mock import call

        tool_agent = _make_agent([
            HumanMessage(content="portfolio?"),
            ToolMessage(content="Holdings: AAPL $5k", name="portfolio_summary", tool_call_id="tc-v1"),
            AIMessage(content="You hold AAPL."),
        ])

        mock_pipeline = AsyncMock(return_value=_TOOL_PIPELINE)

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=tool_agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch("ghostfolio_agent.api.chat.run_verification_pipeline", mock_pipeline),
        ):
            resp = await client.post(
                "/api/chat", json={"message": "portfolio?", "session_id": "s-v1"}
            )

        assert resp.status_code == 200
        mock_pipeline.assert_awaited_once()

    async def test_verification_skipped_without_tool_calls(self, client: httpx.AsyncClient):
        """run_verification_pipeline is NOT called when no tools were invoked."""
        agent = _make_agent([
            HumanMessage(content="hi"),
            AIMessage(content="Hello!"),
        ])

        mock_pipeline = AsyncMock(return_value=_NO_OP_PIPELINE)

        with (
            patch("ghostfolio_agent.api.chat._get_agent", return_value=agent),
            patch("ghostfolio_agent.api.chat._get_alert_engine", return_value=_make_alert_engine()),
            patch("ghostfolio_agent.api.chat.run_verification_pipeline", mock_pipeline),
        ):
            resp = await client.post("/api/chat", json={"message": "hi", "session_id": "s-v2"})

        assert resp.status_code == 200
        mock_pipeline.assert_not_awaited()
