"""Bridge the synchronous orchestrator graph's streaming API to an async SSE generator."""

import logging
from collections.abc import AsyncIterator

from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from app.agents.router import AgentRoute
from app.graph.orchestrator_graph import SetupFailedStream, TapioOrchestratorGraph
from app.grounding import NO_SOURCE_MESSAGE, SourceCitation, format_citations
from app.guardrails import GuardrailClassifierProtocol, GuardrailMatch, build_guardrail_response
from app.schemas import ChatMessage, Citation, CitationEvent, ErrorEvent, GuardrailEvent, RoutingEvent, TokenEvent

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "I encountered an error while processing your query. Please try again."


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


def _citation(source: SourceCitation) -> Citation:
    return Citation(
        title=source.title,
        source_url=source.url,
        snippet=source.snippet,
        crawl_date=source.crawl_date,
        formatted=source.formatted,
    )


async def stream_chat_turn(
    orchestrator_graph: TapioOrchestratorGraph,
    guardrail_classifier: GuardrailClassifierProtocol,
    message: str,
    history: list[ChatMessage],
    agent_id: str,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE-ready events for one chat turn: routing, citation, token(s), then done.

    Citations are built deterministically from the retrieved documents (#114).
    If none of them is citable, the model's answer is never generated: the
    citation event carries ``no_source`` and the reply is ``NO_SOURCE_MESSAGE``.

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
    free. This first call uses ``safe_route`` rather than
    ``agent_router.route()`` directly, since ``ChatRequest.agent_id`` is
    client-supplied and an unrecognized id would otherwise raise here, before
    any SSE event (including ``routing``) is ever yielded.

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
        route = orchestrator_graph.safe_route(message, agent_id)
        yield {"event": "routing", "data": _routing_event(route).model_dump_json()}

        guardrail_match = await guardrail_classifier.classify(message)
        if guardrail_match is not None:
            logger.info("Guardrail intercepted message: %s (%s)", guardrail_match.reason, guardrail_match.category)
            yield {"event": "guardrail", "data": _guardrail_event(guardrail_match).model_dump_json()}
            yield {"event": "citation", "data": CitationEvent(citations=[]).model_dump_json()}
            response_text = await build_guardrail_response(guardrail_match, message)
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

        if isinstance(response_stream, SetupFailedStream):
            # The graph failed before generation; this is an error, not a turn without sources.
            yield {"event": "error", "data": ErrorEvent(message=GENERIC_ERROR_MESSAGE).model_dump_json()}
            return

        sources = format_citations(retrieved_docs)
        citation_event = CitationEvent(citations=[_citation(source) for source in sources], no_source=not sources)
        yield {"event": "citation", "data": citation_event.model_dump_json()}

        if not sources:
            # PRD §7.3: with nothing to cite, say so rather than let the model answer unsourced.
            logger.info("No citable source retrieved; returning the no-source message")
            if hasattr(response_stream, "close"):
                response_stream.close()
            yield {"event": "token", "data": TokenEvent(text=NO_SOURCE_MESSAGE).model_dump_json()}
        else:
            async for chunk in iterate_in_threadpool(response_stream):
                if chunk:
                    yield {"event": "token", "data": TokenEvent(text=chunk).model_dump_json()}

        yield {"event": "done", "data": "{}"}
    except Exception:
        logger.exception("Error streaming chat turn")
        yield {"event": "error", "data": ErrorEvent(message=GENERIC_ERROR_MESSAGE).model_dump_json()}
