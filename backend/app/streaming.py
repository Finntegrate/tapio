"""Bridge the LangGraph-driven, memory-backed chat turn to an async SSE generator."""

import asyncio
import logging
from collections.abc import AsyncIterator

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from app.schemas import ErrorEvent

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "I encountered an error while processing your query. Please try again."


async def stream_chat_turn(
    graph: CompiledStateGraph,
    message: str,
    agent_id: str,
    thread_id: str,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE-ready events for one chat turn: routing, citation, token(s), then done.

    Runs the graph node in the background and relays the ``{"event", "data"}``
    mappings it pushes onto its event queue as they arrive, so the caller sees
    them as they're produced rather than only after the turn completes.

    Args:
        graph: The compiled, checkpointer-backed conversation graph.
        message: The user's current message.
        agent_id: Explicit guide id, or ``AUTO_ROUTE`` to let the router decide.
        thread_id: Conversation id; the checkpointer keys prior turns by this.

    Yields:
        SSE event mappings with ``event`` and ``data`` keys.
    """
    queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
    config: RunnableConfig = {"configurable": {"thread_id": thread_id, "event_queue": queue}}

    async def run_graph() -> None:
        try:
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": message}], "agent_id": agent_id},
                config=config,
            )
        except Exception:
            logger.exception("Error streaming chat turn")
            await queue.put({"event": "error", "data": ErrorEvent(message=GENERIC_ERROR_MESSAGE).model_dump_json()})
        finally:
            await queue.put(None)

    task = asyncio.create_task(run_graph())
    try:
        while (event := await queue.get()) is not None:
            yield event
            if event["event"] == "error":
                return
        yield {"event": "done", "data": "{}"}
    finally:
        await task
