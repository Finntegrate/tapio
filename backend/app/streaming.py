"""Bridge the synchronous orchestrator graph's streaming API to an async SSE generator."""

import logging
from collections.abc import AsyncIterator
from typing import Any

from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from app.agents.router import AgentRoute
from app.graph.orchestrator_graph import TapioOrchestratorGraph
from app.guardrails import GuardrailClassifierProtocol, GuardrailMatch, build_guardrail_response
from app.schemas import ChatMessage, Citation, CitationEvent, ErrorEvent, GuardrailEvent, RoutingEvent, TokenEvent

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


def _guardrail_event(match: GuardrailMatch) -> GuardrailEvent:
    return GuardrailEvent(category=match.category.value, reason=match.reason)


def _citation(document: Any) -> Citation:
    metadata = document.metadata if hasattr(document, "metadata") else {}
    source_url = metadata.get("citation_url") or metadata.get("source_url") or metadata.get("url") or "Unknown source"
    title = metadata.get("title", "Untitled source")
    content = document.page_content if hasattr(document, "page_content") else str(document)
    return Citation(title=title, source_url=source_url, snippet=content[:CITATION_SNIPPET_LENGTH])


async def stream_chat_turn(
    orchestrator_graph: TapioOrchestratorGraph,
    guardrail_classifier: GuardrailClassifierProtocol,
    message: str,
    history: list[ChatMessage],
    agent_id: str,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE-ready events for one chat turn: routing, citation, token(s), then done.

    Mirrors the call sequence in ``tapio.app.TapioAssistantApp`` (route, then
    stream), bridging the orchestrator graph's synchronous retrieval and
    token generator onto the async event loop via Starlette's threadpool
    helpers.

    Before retrieval and generation, the message is classified for guardrail
    handling (#29, PRD §7.4). A crisis-adjacent, legally sensitive, or
    out-of-scope message short-circuits the RAG pipeline's retrieval step
    entirely: an extra ``guardrail`` event is emitted, and the response text
    comes from a small, focused, language-matching LLM call plus (for
    crisis/legal-sensitive matches) deterministically-formatted entries from
    the approved crisis/escalation resource list, rather than a RAG answer.

    The routing decision is made twice on the RAG path (once here, again
    inside the graph's own routing node once ``route.agent.id`` is passed
    back in as an explicit selection) so that a guardrail match can still
    short-circuit retrieval and generation without running them first. Both
    calls are pure keyword scoring (#138) with no LLM cost, so the repeat is
    free.

    Args:
        orchestrator_graph: Shared orchestrator graph built at app startup.
        guardrail_classifier: Shared guardrail classifier built at app startup.
        message: The user's current message.
        history: Prior conversation turns.
        agent_id: Explicit guide id, or ``AUTO_ROUTE`` to let the router decide.

    Yields:
        SSE event mappings with ``event`` and ``data`` keys.
    """
    try:
        route = orchestrator_graph.agent_router.route(message, agent_id)
        yield {"event": "routing", "data": _routing_event(route).model_dump_json()}

        guardrail_match = await guardrail_classifier.classify(message)
        if guardrail_match is not None:
            logger.info("Guardrail intercepted message: %s (%s)", guardrail_match.reason, guardrail_match.category)
            yield {"event": "guardrail", "data": _guardrail_event(guardrail_match).model_dump_json()}
            yield {"event": "citation", "data": CitationEvent(citations=[]).model_dump_json()}
            response_text = await build_guardrail_response(guardrail_match, message, orchestrator_graph.llm_service)
            yield {"event": "token", "data": TokenEvent(text=response_text).model_dump_json()}
            yield {"event": "done", "data": "{}"}
            return

        raw_history = [turn.model_dump() for turn in history]
        _route, response_stream, retrieved_docs = await run_in_threadpool(
            orchestrator_graph.query_stream,
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
