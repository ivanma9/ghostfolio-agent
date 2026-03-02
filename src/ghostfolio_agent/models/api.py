from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's natural language query")
    session_id: str = Field(default="default", description="Session ID for conversation history")
    model: str | None = Field(default=None, description="OpenRouter model ID to use")
    paper_trading: bool = Field(default=False, description="Enable paper trading mode for buy/sell intent")


class Citation(BaseModel):
    claim: str = Field(..., description="The specific claim or data point")
    tool_name: str = Field(..., description="The tool that provided the data")
    source_detail: str = Field(
        default="", description="Specific detail from the tool result supporting the claim"
    )


class AlertItem(BaseModel):
    symbol: str = Field(..., description="Ticker symbol")
    condition: str = Field(..., description="Alert condition key e.g. earnings_proximity")
    message: str = Field(..., description="Human-readable alert message")
    severity: Literal["warning", "critical"] = Field(..., description="Alert severity level")


class AgentStructuredResponse(BaseModel):
    """Schema for the agent's structured final response."""

    response: str = Field(..., description="The natural language response to the user")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Citations linking claims to the tool calls that produced the data",
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="Agent's natural language response")
    session_id: str
    tool_calls: list[str] = Field(default_factory=list, description="Tools that were invoked")
    tool_outputs: list[str] = Field(default_factory=list, description="Raw tool result strings")
    confidence: str = Field(default="high", description="Response confidence: high, medium, low")
    citations: list[Citation] = Field(
        default_factory=list, description="Citations linking claims to tool results"
    )
    verification_issues: list[str] = Field(
        default_factory=list, description="Issues found by the verification pipeline"
    )
    verification_details: dict[str, str] = Field(
        default_factory=dict, description="Per-verifier confidence map"
    )
    data_sources: list[str] = Field(
        default_factory=list, description="3rd-party data sources used in this response"
    )
    alerts: list[AlertItem] = Field(
        default_factory=list, description="Structured alerts fired during this request"
    )


class HealthResponse(BaseModel):
    status: str = "ok"


class PortfolioPositionResponse(BaseModel):
    symbol: str
    name: str
    quantity: float
    price: float
    value: float
    allocation: float
    currency: str


class PortfolioResponse(BaseModel):
    total_value: float
    daily_change: float
    daily_change_percent: float
    positions: list[PortfolioPositionResponse] = Field(default_factory=list)


class PaperPositionResponse(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float
    value: float
    pnl: float
    pnl_percent: float
    allocation: float


class PaperPortfolioResponse(BaseModel):
    cash: float
    total_value: float
    total_pnl: float
    total_pnl_percent: float
    positions: list[PaperPositionResponse] = Field(default_factory=list)
