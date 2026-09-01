"""Throwaway script: proves checkpointer.py + graph.py actually remember across turns.

Not part of the app. Run with: uv run python verify_memory.py
Delete once you trust the result.
"""

import asyncio

from langgraph.checkpoint.memory import MemorySaver

from app.agents.router import AgentRouter
from app.memory.graph import build_graph


class FakeOrchestrator:
    """Stands in for RAGOrchestrator so we're testing memory, not the AI."""

    def query_stream(self, query_text, history, agent_id):
        print(f"  orchestrator received question: {query_text!r}")
        print(f"  orchestrator received history:  {history!r}")
        answer = f"Mocked answer to: {query_text}"
        return iter([answer]), []


async def main():
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer, FakeOrchestrator(), AgentRouter())

    thread_id = "verify-thread-1"

    async def send(message: str):
        queue = asyncio.Queue()
        config = {"configurable": {"thread_id": thread_id, "event_queue": queue}}
        await graph.ainvoke(
            {"messages": [{"role": "user", "content": message}], "agent_id": "auto"},
            config=config,
        )

    print("--- Turn 1 ---")
    await send("How do I apply for a residence permit?")

    print("\n--- Turn 2 (same thread_id) ---")
    await send("What about for students?")

    print("\n--- Checking what's saved ---")
    state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    for m in state.values["messages"]:
        print(f"  [{m.type}] {m.content}")


if __name__ == "__main__":
    asyncio.run(main())
