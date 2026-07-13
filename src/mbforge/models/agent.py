"""Agent chat Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentSessionRequest(BaseModel):
    library_root: str | None = Field(None, description="Library root for the session")
    session_id: str | None = Field(None, description="Optional session ID (auto-generated if omitted)")


class AgentChatRequest(BaseModel):
    user_input: str = Field(..., description="User message")


class AgentInitResponse(BaseModel):
    success: bool = True
    agent_ready: bool = False
    warning: str | None = None


class AgentSessionResponse(BaseModel):
    success: bool = True
    session_id: str


class AgentSessionOkResponse(BaseModel):
    success: bool = True


class AgentHistoryMessage(BaseModel):
    role: str
    content: str


class AgentHistoryResponse(BaseModel):
    success: bool = True
    messages: list[AgentHistoryMessage] = []


class AgentErrorResponse(BaseModel):
    success: bool = False
    error: str


class AgentChatResponse(BaseModel):
    success: bool = True
    reply: str = ""
