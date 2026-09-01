"""LangGraph wrapper around RAGOrchestrator, for conversation persistence."""

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from app.agents.router import AgentRouter
from app.schemas import CitationEvent, TokenEvent
from app.services.rag_orchestrator import RAGOrchestrator
from app.sse_events import citation_from_document, routing_event

logger = logging.getLogger(__name__)

# LangGraph stores messages with .type of "human"/"ai"; the rest of Tapio
# uses "user"/"assistant" role dicts.
_ROLES = {"human": "user", "ai": "assistant"}


def to_history(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    """Convert LangGraph message objects to the role/content dicts Tapio uses."""
    return [{"role": _ROLES.get(m.type, m.type), "content": m.content} for m in messages]


class ChatState(MessagesState):
    """Conversation state plus the guide selected for the current turn."""

    agent_id: str


def build_graph(
    checkpointer: BaseCheckpointSaver,
    orchestrator: RAGOrchestrator,
    agent_router: AgentRouter,
) -> CompiledStateGraph:
    """Compile a one-node graph that persists conversation state and streams SSE events.

    Each invocation must pass an ``event_queue: asyncio.Queue`` in
    ``config["configurable"]``; the node pushes SSE-ready ``{"event", "data"}``
    mappings onto it as the response streams.
    """

    async def call_model(state: ChatState, config: RunnableConfig) -> dict[str, Any]:
        queue: asyncio.Queue[dict[str, str]] = config["configurable"]["event_queue"]
        question = str(state["messages"][-1].content)
        history = to_history(state["messages"][:-1])

        route = agent_router.route(question, state.get("agent_id", "auto"))
        await queue.put({"event": "routing", "data": routing_event(route).model_dump_json()})

        response_stream, retrieved_docs = await run_in_threadpool(
            orchestrator.query_stream,
            query_text=question,
            history=history,
            agent_id=route.agent.id,
        )

        citations = [citation_from_document(document) for document in retrieved_docs]
        await queue.put({"event": "citation", "data": CitationEvent(citations=citations).model_dump_json()})

        chunks: list[str] = []
        async for chunk in iterate_in_threadpool(response_stream):
            if chunk:
                chunks.append(chunk)  # remember it

                await queue.put({"event": "token", "data": TokenEvent(text=chunk).model_dump_json()})  # send it live

        return {"messages": [{"role": "assistant", "content": "".join(chunks)}]}

    # pyrefly rejects any TypedDict here, including langgraph's own MessagesState -
    # https://github.com/facebook/pyrefly false positive against TypedDictLikeV1/V2.
    builder = StateGraph(ChatState)  # pyrefly: ignore
    builder.add_node("call_model", call_model)
    builder.add_edge(START, "call_model")
    builder.add_edge("call_model", END)
    return builder.compile(checkpointer=checkpointer)
