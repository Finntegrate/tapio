"""Compiled LangGraph graph fronting Tapio's routing -> retrieval -> generation flow."""

import logging
from collections.abc import Generator
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import get_agent
from app.agents.router import AUTO_ROUTE, AgentRoute, AgentRouter
from app.graph.nodes import make_generate_node, make_retrieve_node, make_route_node
from app.graph.state import OrchestratorState
from app.services.document_retrieval_service import DocumentRetrievalService
from app.services.llm import LLMProvider

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "I encountered an error while processing your query. Please try again."


class TapioOrchestratorGraph:
    """Routing, retrieval, and specialist generation as an explicit LangGraph graph.

    Unlike the ``RAGOrchestrator``/``AgentRouter`` pair it replaces in the
    FastAPI request path, this graph resolves the guide itself, so callers
    get the resolved ``AgentRoute`` back from ``query()``/``query_stream()``
    instead of having to call ``AgentRouter.route()`` separately first.

    Args:
        agent_router: Router whose keyword-scoring logic backs the routing node.
        doc_retrieval_service: Service backing the retrieval node.
        llm_service: Service backing the generation node.

    Example:
        >>> from app.factories import RAGOrchestratorFactory
        >>> from app.config.config_models import RAGConfig
        >>>
        >>> orchestrator = RAGOrchestratorFactory(RAGConfig()).create_orchestrator()
        >>> route, response, docs = orchestrator.graph.query("What is the processing time?")
    """

    def __init__(
        self,
        agent_router: AgentRouter,
        doc_retrieval_service: DocumentRetrievalService,
        llm_service: LLMProvider,
    ) -> None:
        """Build the graph and store the dependencies its nodes close over.

        Args:
            agent_router: Router whose keyword-scoring logic backs the routing node.
            doc_retrieval_service: Service backing the retrieval node.
            llm_service: Service backing the generation node.
        """
        self.agent_router = agent_router
        self.doc_retrieval_service = doc_retrieval_service
        self.llm_service = llm_service
        self._compiled_graph = self._build_graph()
        logger.info("Initialized Tapio orchestrator graph")

    def _build_graph(self) -> CompiledStateGraph:
        """Assemble the route -> retrieve -> generate ``StateGraph``.

        Returns:
            The compiled graph, ready to invoke.
        """
        # pyrefly: ignore [bad-specialization]
        builder = StateGraph(OrchestratorState)
        # mypy can't resolve StateGraph.add_node's NodeInputT from a plain
        # `OrchestratorState -> dict[str, Any]` callable against this many
        # call/config/writer/store overloads; the runtime contract (a node is
        # just `state -> partial state`) is exactly what these are.
        builder.add_node("route", make_route_node(self.agent_router))  # type: ignore[call-overload]
        builder.add_node("retrieve", make_retrieve_node(self.doc_retrieval_service))  # type: ignore[call-overload]
        builder.add_node("generate", make_generate_node(self.llm_service))  # type: ignore[call-overload]
        builder.add_edge(START, "route")
        builder.add_edge("route", "retrieve")
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", END)
        return builder.compile()

    def query(
        self,
        query_text: str,
        history: list[dict[str, Any]] | None = None,
        agent_id: str = AUTO_ROUTE,
    ) -> tuple[AgentRoute, str, list[Any]]:
        """Run the graph to completion and return a single response.

        Args:
            query_text: The user's query.
            history: Chat history (optional).
            agent_id: An explicit guide id, or ``AUTO_ROUTE`` to infer one.

        Returns:
            The resolved route, the response text, and the retrieved documents.
        """
        try:
            result = self._invoke(query_text, history, agent_id, stream=False)
        except Exception:
            logger.exception("Error generating RAG response")
            return self.safe_route(query_text, agent_id), GENERIC_ERROR_MESSAGE, []

        return result["route"], result["response"], result["retrieved_docs"]

    def query_stream(
        self,
        query_text: str,
        history: list[dict[str, Any]] | None = None,
        agent_id: str = AUTO_ROUTE,
    ) -> tuple[AgentRoute, Generator[str], list[Any]]:
        """Run routing and retrieval eagerly, then return a lazily-consumed response stream.

        Args:
            query_text: The user's query.
            history: Chat history (optional).
            agent_id: An explicit guide id, or ``AUTO_ROUTE`` to infer one.

        Returns:
            The resolved route, a generator of response chunks, and the retrieved documents.
        """
        try:
            result = self._invoke(query_text, history, agent_id, stream=True)
        except Exception:
            logger.exception("Error in query_stream setup")

            def error_generator() -> Generator[str]:
                """Yield the single generic error chunk in place of a real response stream."""
                yield GENERIC_ERROR_MESSAGE

            return self.safe_route(query_text, agent_id), error_generator(), []

        upstream_stream = result["response_stream"]

        def stream_generator() -> Generator[str]:
            """Relay the LLM's chunks, substituting a generic error if it fails mid-stream."""
            try:
                logger.info("Starting to consume LLM response stream")
                yield from upstream_stream
            except Exception:
                logger.exception("Error in stream generator")
                yield GENERIC_ERROR_MESSAGE
            finally:
                if hasattr(upstream_stream, "close"):
                    upstream_stream.close()

        return result["route"], stream_generator(), result["retrieved_docs"]

    def check_model_availability(self) -> bool:
        """Check if the LLM model is available.

        Returns:
            bool: True if the model is available, False otherwise
        """
        return self.llm_service.check_model_availability()

    def format_documents_for_display(self, documents: list[Any]) -> str:
        """Format retrieved documents for display.

        Args:
            documents: List of retrieved documents

        Returns:
            Formatted string containing document information
        """
        return self.doc_retrieval_service.format_documents_for_display(documents)

    def safe_route(self, query_text: str, agent_id: str) -> AgentRoute:
        """Resolve a route the way ``AgentRouter.route()`` would, without ever raising.

        ``AgentRouter.route()`` looks an explicit ``agent_id`` up via
        ``get_agent()``, which raises for an unknown id - streaming.py's
        pre-guardrail routing call, and this graph's own generic-error
        fallback in ``query()``/``query_stream()``, both need a route to
        report even when the id they were given doesn't resolve to a real
        guide, so both call this instead of ``self.agent_router.route()``
        directly.

        Args:
            query_text: The user's query.
            agent_id: An explicit guide id, or ``AUTO_ROUTE`` to infer one.

        Returns:
            The resolved route, or a Tapio fallback if resolving it failed.
        """
        try:
            return self.agent_router.route(query_text, agent_id)
        except Exception:
            logger.exception("Error resolving fallback route for generic error response")
            return AgentRoute(
                agent=get_agent("tapio"),
                reason="Tapio is standing in after an error resolving your selected guide.",
                was_explicit=False,
            )

    def _invoke(
        self,
        query_text: str,
        history: list[dict[str, Any]] | None,
        agent_id: str,
        *,
        stream: bool,
    ) -> OrchestratorState:
        """Run the compiled graph for one turn.

        Args:
            query_text: The user's query.
            history: Chat history (optional).
            agent_id: An explicit guide id, or ``AUTO_ROUTE`` to infer one.
            stream: Whether the generation node should stream its response.

        Returns:
            The graph's final state.
        """
        return cast(
            "OrchestratorState",
            self._compiled_graph.invoke(
                {
                    "query_text": query_text,
                    "history": history,
                    "preferred_agent_id": agent_id,
                    "stream": stream,
                },
            ),
        )
