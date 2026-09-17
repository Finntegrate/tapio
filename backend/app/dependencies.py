"""FastAPI dependency providers for the shared orchestrator and agent router."""

from typing import Annotated

from fastapi import Depends, Request

from app.graph.orchestrator_graph import TapioOrchestratorGraph
from app.guardrails import GuardrailClassifierProtocol
from app.services.rag_orchestrator import RAGOrchestrator


def get_orchestrator(request: Request) -> RAGOrchestrator:
    """Return the orchestrator instance built during app startup.

    Args:
        request: The current request, used to reach ``app.state``.

    Returns:
        The shared ``RAGOrchestrator`` singleton.
    """
    return request.app.state.orchestrator


def get_orchestrator_graph(request: Request) -> TapioOrchestratorGraph:
    """Return the orchestrator graph instance built during app startup.

    Args:
        request: The current request, used to reach ``app.state``.

    Returns:
        The shared ``TapioOrchestratorGraph`` singleton (see ``app.graph``), which
        the chat route uses directly for routing, retrieval, and generation.
    """
    return request.app.state.orchestrator_graph


def get_guardrail_classifier(request: Request) -> GuardrailClassifierProtocol:
    """Return the guardrail classifier instance built during app startup.

    Args:
        request: The current request, used to reach ``app.state``.

    Returns:
        The shared guardrail classifier singleton (see ``app.guardrails.LLMGuardrailClassifier``).
    """
    return request.app.state.guardrail_classifier


OrchestratorDep = Annotated[RAGOrchestrator, Depends(get_orchestrator)]
OrchestratorGraphDep = Annotated[TapioOrchestratorGraph, Depends(get_orchestrator_graph)]
GuardrailClassifierDep = Annotated[GuardrailClassifierProtocol, Depends(get_guardrail_classifier)]
