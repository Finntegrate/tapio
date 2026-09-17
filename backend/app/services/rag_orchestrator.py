"""RAG orchestrator service that coordinates document retrieval and LLM generation.

As of #138, the actual coordination lives in ``TapioOrchestratorGraph``
(``app.graph.orchestrator_graph``): a LangGraph ``StateGraph`` with explicit
routing, retrieval, and generation nodes. This class is now a thin,
backward-compatible facade over that graph, kept for callers (tests,
scripts, notebooks) that want a simple, non-graph-aware orchestrator whose
``agent_id`` is always an explicit guide selection rather than something to
auto-route. The FastAPI chat route talks to the graph directly (see
``app.graph``, ``app.dependencies.OrchestratorGraphDep``) via
``self.graph``, since it also needs the resolved ``AgentRoute``.
"""

import logging
from collections.abc import Generator
from typing import Any

from app.agents.router import AgentRouter
from app.graph.orchestrator_graph import TapioOrchestratorGraph
from app.services.document_retrieval_service import DocumentRetrievalService
from app.services.llm import LLMProvider

# Configure logging
logger = logging.getLogger(__name__)


class RAGOrchestrator:
    """Orchestrates document retrieval and LLM generation for RAG workflow.

    This orchestrator coordinates the RAG pipeline by combining document retrieval
    with LLM generation. All dependencies are injected to enable testing and
    allow reuse of configured service instances.
    """

    def __init__(
        self,
        doc_retrieval_service: DocumentRetrievalService,
        llm_service: LLMProvider,
    ) -> None:
        """Initialize the RAG orchestrator.

        Args:
            doc_retrieval_service: Service for retrieving documents from vector store
            llm_service: Provider for LLM generation

        Example:
            >>> from app.factories import RAGOrchestratorFactory
            >>> from app.config.config_models import RAGConfig
            >>>
            >>> config = RAGConfig(collection_name="my_docs")
            >>> factory = RAGOrchestratorFactory(config)
            >>> orchestrator = factory.create_orchestrator()
            >>>
            >>> # Or manually for advanced use cases:
            >>> doc_service = DocumentRetrievalService(vector_store=my_store)
            >>> llm_service = OllamaProvider(model_name="gemma4:latest")
            >>> orchestrator = RAGOrchestrator(doc_service, llm_service)
        """
        self.doc_retrieval_service = doc_retrieval_service
        self.llm_service = llm_service
        self.graph = TapioOrchestratorGraph(
            agent_router=AgentRouter(),
            doc_retrieval_service=doc_retrieval_service,
            llm_service=llm_service,
        )

        logger.info(
            "Initialized RAG orchestrator",
        )

    def query(
        self,
        query_text: str,
        history: list[dict[str, Any]] | None = None,
        agent_id: str = "tapio",
    ) -> tuple[str, list[Any]]:
        """Generate a response using RAG.

        Args:
            query_text: The user's query
            history: Chat history (optional)
            agent_id: The guide whose specialist system prompt should be applied

        Returns:
            Tuple containing the response and the retrieved documents
        """
        _route, response, retrieved_docs = self.graph.query(query_text, history, agent_id)
        return response, retrieved_docs

    def query_stream(
        self,
        query_text: str,
        history: list[dict[str, Any]] | None = None,
        agent_id: str = "tapio",
    ) -> tuple[Generator[str], list[Any]]:
        """Generate a streaming response using RAG.

        Args:
            query_text: The user's query
            history: Chat history (optional)
            agent_id: The guide whose specialist system prompt should be applied

        Returns:
            Tuple containing the response generator and the retrieved documents
        """
        _route, response_stream, retrieved_docs = self.graph.query_stream(query_text, history, agent_id)
        return response_stream, retrieved_docs

    def check_model_availability(self) -> bool:
        """Check if the LLM model is available.

        Returns:
            bool: True if the model is available, False otherwise
        """
        return self.graph.check_model_availability()

    def format_documents_for_display(self, documents: list[Any]) -> str:
        """Format retrieved documents for display.

        Args:
            documents: List of retrieved documents

        Returns:
            Formatted string containing document information
        """
        return self.doc_retrieval_service.format_documents_for_display(documents)
