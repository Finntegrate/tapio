"""Streaming chat endpoint."""

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.dependencies import GuardrailClassifierDep, OrchestratorGraphDep
from app.schemas import ChatRequest
from app.streaming import stream_chat_turn

router = APIRouter()


@router.post("/chat/stream")
async def chat_stream(
    chat_request: ChatRequest,
    orchestrator_graph: OrchestratorGraphDep,
    guardrail_classifier: GuardrailClassifierDep,
) -> EventSourceResponse:
    """Stream one chat turn as Server-Sent Events: routing, citation, token(s), done.

    Args:
        chat_request: The user's message, history, and optional guide selection.
        orchestrator_graph: Shared LangGraph orchestrator graph, injected.
        guardrail_classifier: Shared guardrail classifier, injected.

    Returns:
        An SSE response streaming the turn's events as they become available.
    """
    events = stream_chat_turn(
        orchestrator_graph=orchestrator_graph,
        guardrail_classifier=guardrail_classifier,
        message=chat_request.message,
        history=chat_request.history,
        agent_id=chat_request.agent_id,
    )
    return EventSourceResponse(events)
