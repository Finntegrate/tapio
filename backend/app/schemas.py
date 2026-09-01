"""Request/response and SSE event payload models for the chat API."""

from pydantic import BaseModel, Field

from app.agents.router import AUTO_ROUTE


class ChatRequest(BaseModel):
    """Body of ``POST /chat/stream``.

    ``thread_id`` scopes conversation memory: the same id across requests
    lets the checkpointer recall prior turns, so history no longer needs to
    travel over the wire.
    """

    message: str = Field(min_length=1)
    agent_id: str = AUTO_ROUTE
    thread_id: str = Field(min_length=1)


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
