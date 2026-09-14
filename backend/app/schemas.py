"""Request/response and SSE event payload models for the chat API."""

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.router import AUTO_ROUTE


class ChatMessage(BaseModel):
    """One turn of prior conversation history, OpenAI-style."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Body of ``POST /chat/stream``."""

    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    agent_id: str = AUTO_ROUTE


class AgentSummary(BaseModel):
    """User-facing guide summary returned by ``GET /agents``."""

    id: str
    name: str
    title: str
    category: str
    summary: str
    color: str


class RoutingEvent(BaseModel):
    """Which guide was selected for this turn, and why."""

    agent_id: str
    name: str
    title: str
    category: str
    reason: str
    was_explicit: bool


class Citation(BaseModel):
    """A single retrieved source backing the response."""

    title: str
    source_url: str
    snippet: str


class CitationEvent(BaseModel):
    """Sources retrieved for this turn."""

    citations: list[Citation]


class TokenEvent(BaseModel):
    """One chunk of streamed assistant text."""

    text: str


class ErrorEvent(BaseModel):
    """A generic, user-safe error message."""

    message: str


class HealthResponse(BaseModel):
    """Result of the Ollama/model availability check."""

    model_available: bool
