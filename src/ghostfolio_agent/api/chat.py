import asyncio
import os
import sqlite3

import structlog
from fastapi import APIRouter, HTTPException
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from ghostfolio_agent.models.api import Citation, ChatRequest, ChatResponse, PaperPositionResponse, PaperPortfolioResponse, PortfolioPositionResponse, PortfolioResponse
from ghostfolio_agent.tools.paper_trade import load_portfolio, _STARTING_CASH

logger = structlog.get_logger()
from ghostfolio_agent.agent.graph import create_agent, AVAILABLE_MODELS, DEFAULT_MODEL
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient
from ghostfolio_agent.config import get_settings
from ghostfolio_agent.verification.pipeline import run_verification_pipeline
from ghostfolio_agent.alerts.engine import AlertEngine

router = APIRouter()

# Shared state
_client: GhostfolioClient | None = None
_checkpointer: SqliteSaver | None = None
_agents: dict[str, object] = {}  # model_name -> agent
_alert_engine: AlertEngine | None = None


def _get_alert_engine() -> AlertEngine:
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine()
    return _alert_engine


def _get_client() -> GhostfolioClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = GhostfolioClient(
            base_url=settings.ghostfolio_base_url,
            access_token=settings.ghostfolio_access_token,
        )
    return _client


_DB_PATH = "data/checkpoints.db"


def _get_checkpointer() -> SqliteSaver:
    global _checkpointer
    if _checkpointer is None:
        db_dir = os.path.dirname(_DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _checkpointer = SqliteSaver(conn)
    return _checkpointer


def _get_agent(model_name: str = DEFAULT_MODEL):
    global _agents
    if model_name not in _agents:
        settings = get_settings()
        finnhub = FinnhubClient(api_key=settings.finnhub_api_key) if settings.finnhub_api_key else None
        alpha_vantage = AlphaVantageClient(api_key=settings.alpha_vantage_api_key) if settings.alpha_vantage_api_key else None
        fmp = FMPClient(api_key=settings.fmp_api_key) if settings.fmp_api_key else None
        _agents[model_name] = create_agent(
            _get_client(),
            openrouter_api_key=settings.openrouter_api_key,
            openai_api_key=settings.openai_api_key,
            model_name=model_name,
            checkpointer=_get_checkpointer(),
            max_context_messages=settings.max_context_messages,
            finnhub=finnhub,
            alpha_vantage=alpha_vantage,
            fmp=fmp,
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


@router.get("/api/portfolio", response_model=PortfolioResponse)
async def get_portfolio():
    """Return real portfolio holdings with daily change — no LLM call needed."""
    try:
        client = _get_client()
        holdings_data, perf_data = await asyncio.gather(
            client.get_portfolio_holdings(),
            client.get_portfolio_performance("1d"),
        )

        raw_holdings = holdings_data.get("holdings", {})
        if isinstance(raw_holdings, dict):
            holdings = list(raw_holdings.values())
        else:
            holdings = list(raw_holdings)

        total_value = 0.0
        positions: list[PortfolioPositionResponse] = []
        for h in holdings:
            value = h.get("valueInBaseCurrency", 0) or 0
            total_value += value
            positions.append(PortfolioPositionResponse(
                symbol=h.get("symbol", "?"),
                name=h.get("name") or h.get("symbol", "?"),
                quantity=h.get("quantity", 0) or 0,
                price=h.get("marketPrice", 0) or 0,
                value=value,
                allocation=round((h.get("allocationInPercentage", 0) or 0) * 100, 1),
                currency=h.get("currency", "USD"),
            ))

        # Extract daily change from performance data
        perf = perf_data.get("chart", [{}])
        daily_change = perf_data.get("netPerformance", 0) or 0
        daily_change_pct = (perf_data.get("netPerformancePercentage", 0) or 0) * 100

        return PortfolioResponse(
            total_value=total_value,
            daily_change=daily_change,
            daily_change_percent=daily_change_pct,
            positions=positions,
        )
    except Exception as e:
        logger.error("portfolio_endpoint_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load portfolio.")


@router.get("/api/paper-portfolio", response_model=PaperPortfolioResponse)
async def get_paper_portfolio():
    """Return paper portfolio with live prices — no LLM call needed."""
    try:
        portfolio = load_portfolio()
        cash = portfolio.get("cash", _STARTING_CASH)
        positions_raw = portfolio.get("positions", {})

        client = _get_client()
        positions: list[PaperPositionResponse] = []
        total_position_value = 0.0

        if positions_raw:
            # Fetch live prices in parallel
            async def _price(sym: str, pos: dict) -> PaperPositionResponse:
                avg_cost = pos.get("avg_cost", 0)
                qty = pos.get("quantity", 0)
                current_price = avg_cost  # fallback
                try:
                    lookup = await client.lookup_symbol(sym)
                    items = lookup.get("items", [])
                    if items:
                        ds = items[0].get("dataSource", "YAHOO")
                        sym_data = await client.get_symbol(ds, sym)
                        current_price = sym_data.get("marketPrice", avg_cost) or avg_cost
                except Exception:
                    pass
                value = qty * current_price
                cost = qty * avg_cost
                pnl = value - cost
                pnl_pct = (pnl / cost * 100) if cost else 0
                return PaperPositionResponse(
                    symbol=sym,
                    quantity=qty,
                    avg_cost=avg_cost,
                    current_price=current_price,
                    value=value,
                    pnl=pnl,
                    pnl_percent=pnl_pct,
                    allocation=0,  # filled below
                )

            results = await asyncio.gather(
                *[_price(sym, pos) for sym, pos in positions_raw.items()]
            )
            positions = list(results)
            total_position_value = sum(p.value for p in positions)

            # Compute allocations
            total_value = cash + total_position_value
            if total_value > 0:
                for p in positions:
                    p.allocation = round(p.value / total_value * 100, 1)

        total_value = cash + total_position_value
        total_pnl = total_value - _STARTING_CASH
        total_pnl_pct = (total_pnl / _STARTING_CASH * 100)

        return PaperPortfolioResponse(
            cash=cash,
            total_value=total_value,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_pct,
            positions=positions,
        )
    except Exception as e:
        logger.error("paper_portfolio_endpoint_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load paper portfolio.")


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    logger.info("chat_request", session_id=request.session_id, model=request.model)
    try:
        model = request.model or DEFAULT_MODEL
        agent = _get_agent(model)

        # Wrap message with paper trading instruction if enabled
        content = request.message
        if request.paper_trading:
            content = (
                f"[PAPER TRADING MODE ACTIVE] "
                f"IMPORTANT: You MUST use the paper_trade tool for ALL buy/sell/trade requests. "
                f"Do NOT use activity_log or ask for confirmation — execute immediately with paper_trade. "
                f"The paper_trade tool accepts: 'buy 10 AAPL', 'sell 5 NVDA', or 'buy $300 MU'. "
                f"It fetches prices and resolves symbols automatically — do NOT call symbol_lookup first. "
                f"Just pass the user's intent directly as the action string. "
                f"User message: {request.message}"
            )

        # Run alert check
        alert_engine = _get_alert_engine()
        settings = get_settings()
        finnhub = FinnhubClient(api_key=settings.finnhub_api_key) if settings.finnhub_api_key else None
        alpha_vantage_client = AlphaVantageClient(api_key=settings.alpha_vantage_api_key) if settings.alpha_vantage_api_key else None
        fmp_client = FMPClient(api_key=settings.fmp_api_key) if settings.fmp_api_key else None

        try:
            alerts = await alert_engine.check_alerts(
                _get_client(), finnhub=finnhub, alpha_vantage=alpha_vantage_client, fmp=fmp_client
            )
        except Exception as e:
            logger.warning("alert_check_failed", error=str(e))
            alerts = []

        if alerts:
            alert_block = "ALERTS:\n" + "\n".join(f"- {a}" for a in alerts)
            content = f"{alert_block}\n\nUser message: {content}"

        # Checkpointer manages history per thread_id — only send the new message
        config = {"configurable": {"thread_id": request.session_id}}

        try:
            async with asyncio.timeout(90):
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=content)]},
                    config=config,
                )
        except TimeoutError:
            logger.warning("chat_request_timeout", session_id=request.session_id)
            return ChatResponse(
                response="The request took too long. Please try again — if the issue persists, try a different model.",
                session_id=request.session_id,
                tool_calls=[],
                tool_outputs=[],
                confidence="low",
                citations=[],
            )
        except GraphInterrupt as gi:
            # Human-in-the-loop: activity_log interrupted for confirmation
            prompt = gi.args[0] if gi.args else "Please confirm this action."
            return ChatResponse(
                response=str(prompt),
                session_id=request.session_id,
                tool_calls=[],
                tool_outputs=[],
                confidence="high",
                citations=[],
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

        # Run full verification pipeline
        client = _get_client()
        pipeline_result = await run_verification_pipeline(
            response_text=ai_response,
            tool_outputs=tool_outputs,
            client=client if ai_response else None,
        )

        # Build per-verifier confidence details
        verification_details: dict[str, str] = {}
        if pipeline_result.numerical:
            verification_details["numerical"] = pipeline_result.numerical.confidence
        if pipeline_result.hallucination:
            verification_details["hallucination"] = pipeline_result.hallucination.confidence
        if pipeline_result.output_validation:
            verification_details["output_validation"] = pipeline_result.output_validation.confidence
        if pipeline_result.domain_constraints:
            verification_details["domain_constraints"] = pipeline_result.domain_constraints.confidence

        return ChatResponse(
            response=pipeline_result.response_text,
            session_id=request.session_id,
            tool_calls=list(set(tool_calls_made)),
            tool_outputs=tool_outputs,
            confidence=pipeline_result.overall_confidence,
            citations=citations,
            verification_issues=pipeline_result.all_issues,
            verification_details=verification_details,
        )
    except Exception as e:
        logger.error("chat_endpoint_failed", error=str(e), session_id=request.session_id)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
