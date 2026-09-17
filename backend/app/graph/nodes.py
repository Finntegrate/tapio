"""Node functions for Tapio's orchestrator graph.

Each ``make_*_node`` factory closes over the dependency it needs (the agent
router, or a service) and returns a plain ``state -> partial state`` callable
suitable for ``StateGraph.add_node``. The logic inside each node is carried
over unchanged from ``AgentRouter.route()`` and the old ``RAGOrchestrator``
methods (#138) - only the wiring between them changed.
"""

import logging
from collections.abc import Callable
from typing import Any

from app.agents import get_agent
from app.agents.router import AUTO_ROUTE, AgentRouter
from app.graph.state import OrchestratorState
from app.prompts import load_prompt
from app.services.document_retrieval_service import DocumentRetrievalService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

NodeFn = Callable[[OrchestratorState], dict[str, Any]]


def build_system_prompt(agent_id: str) -> str:
    """Combine Tapio's safety baseline with a specialist's scope when needed.

    Args:
        agent_id: Identifier for the guide whose specialist prompt may be loaded.

    Returns:
        The shared prompt, optionally extended with a specialist prompt.
    """
    base_prompt = load_prompt("system_prompt")
    agent = get_agent(agent_id)
    if agent.specialist_prompt is None:
        return base_prompt

    specialist_prompt = load_prompt(agent.specialist_prompt)
    return f"{base_prompt}\n\n{specialist_prompt}".strip()


def make_route_node(agent_router: AgentRouter) -> NodeFn:
    """Build the routing node: selects a guide via ``AgentRouter``.

    Args:
        agent_router: Router whose keyword-scoring logic decides the guide.

    Returns:
        A node callable that populates ``state["route"]``.
    """

    def route_node(state: OrchestratorState) -> dict[str, Any]:
        route = agent_router.route(state["query_text"], state.get("preferred_agent_id", AUTO_ROUTE))
        return {"route": route}

    return route_node


def make_retrieve_node(doc_retrieval_service: DocumentRetrievalService) -> NodeFn:
    """Build the retrieval node: fetches and formats context documents.

    Args:
        doc_retrieval_service: Service used to query the vector store.

    Returns:
        A node callable that populates ``retrieved_docs`` and ``context_text``.
    """

    def retrieve_node(state: OrchestratorState) -> dict[str, Any]:
        retrieved_docs = doc_retrieval_service.retrieve_documents(state["query_text"])
        context_text = doc_retrieval_service.format_documents_as_context(retrieved_docs)
        return {"retrieved_docs": retrieved_docs, "context_text": context_text}

    return retrieve_node


def make_generate_node(llm_service: LLMService) -> NodeFn:
    """Build the specialist generation node: prompts and calls the LLM.

    Args:
        llm_service: Service used to generate the response, streamed or not.

    Returns:
        A node callable that populates the prompts plus ``response`` or
        ``response_stream``, depending on ``state["stream"]``.
    """

    def generate_node(state: OrchestratorState) -> dict[str, Any]:
        system_prompt = build_system_prompt(state["route"].agent.id)
        user_prompt = load_prompt(
            "user_query",
            context=state["context_text"],
            question=state["query_text"],
        )
        history = state.get("history")

        if state.get("stream"):
            logger.info("Generating streaming response with LLM")
            response_stream = llm_service.generate_response_stream(
                prompt=user_prompt,
                system_prompt=system_prompt,
                history=history,
            )
            return {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_stream": response_stream,
            }

        logger.info("Generating response with LLM")
        response = llm_service.generate_response(
            prompt=user_prompt,
            system_prompt=system_prompt,
            history=history,
        )
        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response": str(response),
        }

    return generate_node
