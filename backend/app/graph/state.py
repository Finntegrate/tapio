"""Shared state schema threaded through the orchestrator graph's nodes."""

from collections.abc import Generator
from typing import Any, TypedDict

from app.agents.router import AgentRoute


class OrchestratorState(TypedDict, total=False):
    """State passed between the route, retrieve, and generate nodes.

    ``total=False`` because each node only reads keys earlier nodes populated
    and only returns the keys it owns; LangGraph merges each node's partial
    return into this shared state.
    """

    query_text: str
    history: list[dict[str, Any]] | None
    preferred_agent_id: str
    stream: bool
    route: AgentRoute
    retrieved_docs: list[Any]
    context_text: str
    system_prompt: str
    user_prompt: str
    response: str
    response_stream: Generator[str]
