from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's natural language query")
    session_id: str = Field(default="default", description="Session ID for conversation history")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Agent's natural language response")
    session_id: str
    tool_calls: list[str] = Field(default_factory=list, description="Tools that were invoked")
    confidence: str = Field(default="high", description="Response confidence: high, medium, low")


class HealthResponse(BaseModel):
    status: str = "ok"
