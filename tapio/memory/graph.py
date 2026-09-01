"""LangGraph wrapper around RAGOrchestrator, for conversation persistence."""

from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from tapio.services.rag_orchestrator import RAGOrchestrator

# LangGraph stores messages with .type of "human"/"ai"; the rest of Tapio
# uses "user"/"assistant" role dicts.
_ROLES = {"human": "user", "ai": "assistant"}


def to_history(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Convert LangGraph message objects to the role/content dicts Tapio uses.

    Args:
        messages: Message objects from graph state

    Returns:
        List of role/content dicts
    """
    return [
        {"role": _ROLES.get(m.type, m.type), "content": m.content}
        for m in messages
    ]


def build_graph(
    checkpointer: BaseCheckpointSaver,
    orchestrator: RAGOrchestrator,
) -> CompiledStateGraph:
    """Compile a one-node graph that persists conversation state.

    Args:
        checkpointer: Where conversation state is loaded from and saved to
        orchestrator: Configured RAG orchestrator, called unchanged by the node

    Returns:
        Compiled graph, invoked with a thread_id in the config
    """

    def call_model(state: MessagesState) -> dict[str, Any]:
        question = state["messages"][-1].content
        # query() takes the question separately, so exclude it from history
        history = to_history(state["messages"][:-1])

        answer, _docs = orchestrator.query(query_text=question, history=history)

        return {"messages": [{"role": "assistant", "content": answer}]}

    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    builder.add_edge(START, "call_model")
    builder.add_edge("call_model", END)
    return builder.compile(checkpointer=checkpointer)