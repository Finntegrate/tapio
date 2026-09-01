"""Streaming chat endpoint."""

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.dependencies import GraphDep
from app.schemas import ChatRequest
from app.streaming import stream_chat_turn

router = APIRouter()


@router.post("/chat/stream")
async def chat_stream(
    chat_request: ChatRequest,
    graph: GraphDep,
) -> EventSourceResponse:
    """Stream one chat turn as Server-Sent Events: routing, citation, token(s), done.

    Args:
        chat_request: The user's message, guide selection, and conversation thread id.
        graph: Shared, checkpointer-backed conversation graph, injected.

    Returns:
        An SSE response streaming the turn's events as they become available.
    """
    events = stream_chat_turn(
        graph=graph,
        message=chat_request.message,
        agent_id=chat_request.agent_id,
        thread_id=chat_request.thread_id,
    )
    return EventSourceResponse(events)
