"""FastAPI dependency providers for the shared orchestrator and agent router."""

from typing import Annotated

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph

from app.agents.router import AgentRouter
from app.services.rag_orchestrator import RAGOrchestrator


def get_orchestrator(request: Request) -> RAGOrchestrator:
    """Return the orchestrator instance built during app startup.

    Args:
        request: The current request, used to reach ``app.state``.

    Returns:
        The shared ``RAGOrchestrator`` singleton.
    """
    return request.app.state.orchestrator


def get_agent_router(request: Request) -> AgentRouter:
    """Return the agent router instance built during app startup.

    Args:
        request: The current request, used to reach ``app.state``.

    Returns:
        The shared ``AgentRouter`` singleton.
    """
    return request.app.state.agent_router


def get_graph(request: Request) -> CompiledStateGraph:
    """Return the memory-backed conversation graph built during app startup.

    Args:
        request: The current request, used to reach ``app.state``.

    Returns:
        The shared, checkpointer-backed conversation graph.
    """
    return request.app.state.graph


OrchestratorDep = Annotated[RAGOrchestrator, Depends(get_orchestrator)]
AgentRouterDep = Annotated[AgentRouter, Depends(get_agent_router)]
GraphDep = Annotated[CompiledStateGraph, Depends(get_graph)]
