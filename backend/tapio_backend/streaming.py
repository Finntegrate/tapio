"""Bridge the synchronous RAGOrchestrator streaming API to an async SSE generator."""

import logging
from collections.abc import AsyncIterator
from typing import Any

from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from tapio_backend.agents.router import AgentRoute, AgentRouter
from tapio_backend.schemas import ChatMessage, Citation, CitationEvent, ErrorEvent, RoutingEvent, TokenEvent
from tapio_backend.services.rag_orchestrator import RAGOrchestrator

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "I encountered an error while processing your query. Please try again."
CITATION_SNIPPET_LENGTH = 280


def _routing_event(route: AgentRoute) -> RoutingEvent:
    return RoutingEvent(
        agent_id=route.agent.id,
        name=route.agent.name,
        title=route.agent.title,
        category=route.agent.category,
        reason=route.reason,
        was_explicit=route.was_explicit,
    )


def _citation(document: Any) -> Citation:
    metadata = document.metadata if hasattr(document, "metadata") else {}
    source_url = metadata.get("citation_url") or metadata.get("source_url") or metadata.get("url") or "Unknown source"
    title = metadata.get("title", "Untitled source")
    content = document.page_content if hasattr(document, "page_content") else str(document)
    return Citation(title=title, source_url=source_url, snippet=content[:CITATION_SNIPPET_LENGTH])


async def stream_chat_turn(
    orchestrator: RAGOrchestrator,
    agent_router: AgentRouter,
    message: str,
    history: list[ChatMessage],
    agent_id: str,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE-ready events for one chat turn: routing, citation, token(s), then done.

    Mirrors the call sequence in ``tapio.app.TapioAssistantApp`` (route, then
    stream), bridging its synchronous retrieval and token generator onto the
    async event loop via Starlette's threadpool helpers.

    Args:
        orchestrator: Shared RAG orchestrator built at app startup.
        agent_router: Shared agent router built at app startup.
        message: The user's current message.
        history: Prior conversation turns.
        agent_id: Explicit guide id, or ``AUTO_ROUTE`` to let the router decide.

    Yields:
        SSE event mappings with ``event`` and ``data`` keys.
    """
    try:
        route = agent_router.route(message, agent_id)
        yield {"event": "routing", "data": _routing_event(route).model_dump_json()}

        raw_history = [turn.model_dump() for turn in history]
        response_stream, retrieved_docs = await run_in_threadpool(
            orchestrator.query_stream,
            query_text=message,
            history=raw_history,
            agent_id=route.agent.id,
        )

        citations = [_citation(document) for document in retrieved_docs]
        yield {"event": "citation", "data": CitationEvent(citations=citations).model_dump_json()}

        async for chunk in iterate_in_threadpool(response_stream):
            if chunk:
                yield {"event": "token", "data": TokenEvent(text=chunk).model_dump_json()}

        yield {"event": "done", "data": "{}"}
    except Exception:
        logger.exception("Error streaming chat turn")
        yield {"event": "error", "data": ErrorEvent(message=GENERIC_ERROR_MESSAGE).model_dump_json()}
