"""Build SSE event payloads shared by the stateless and memory-backed chat streams."""

from typing import Any

from app.agents.router import AgentRoute
from app.schemas import Citation, RoutingEvent

CITATION_SNIPPET_LENGTH = 280


def routing_event(route: AgentRoute) -> RoutingEvent:
    """Describe which guide was selected for this turn."""
    return RoutingEvent(
        agent_id=route.agent.id,
        name=route.agent.name,
        title=route.agent.title,
        category=route.agent.category,
        reason=route.reason,
        was_explicit=route.was_explicit,
    )


def citation_from_document(document: Any) -> Citation:
    """Convert a retrieved document into a user-facing citation."""
    metadata = document.metadata if hasattr(document, "metadata") else {}
    source_url = metadata.get("citation_url") or metadata.get("source_url") or metadata.get("url") or "Unknown source"
    title = metadata.get("title", "Untitled source")
    content = document.page_content if hasattr(document, "page_content") else str(document)
    return Citation(title=title, source_url=source_url, snippet=content[:CITATION_SNIPPET_LENGTH])
