from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's natural language query")
    session_id: str = Field(default="default", description="Session ID for conversation history")


class Citation(BaseModel):
    claim: str = Field(..., description="The specific claim or data point")
    tool_name: str = Field(..., description="The tool that provided the data")
    source_detail: str = Field(
        default="", description="Specific detail from the tool result supporting the claim"
    )


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
    confidence: str = Field(default="high", description="Response confidence: high, medium, low")
    citations: list[Citation] = Field(
        default_factory=list, description="Citations linking claims to tool results"
    )


class HealthResponse(BaseModel):
    status: str = "ok"
