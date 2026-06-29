"""RAG orchestrator service that coordinates document retrieval and LLM generation."""

import logging
from collections.abc import Generator
from typing import Any

from tapio.prompts import load_prompt
from tapio.services.document_retrieval_service import DocumentRetrievalService
from tapio.services.llm_service import LLMService

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
        llm_service: LLMService,
    ) -> None:
        """Initialize the RAG orchestrator.

        Args:
            doc_retrieval_service: Service for retrieving documents from vector store
            llm_service: Service for LLM generation

        Example:
            >>> from tapio.factories import RAGOrchestratorFactory
            >>> from tapio.config.config_models import RAGConfig
            >>>
            >>> config = RAGConfig(collection_name="my_docs")
            >>> factory = RAGOrchestratorFactory(config)
            >>> orchestrator = factory.create_orchestrator()
            >>>
            >>> # Or manually for advanced use cases:
            >>> doc_service = DocumentRetrievalService(vector_store=my_store)
            >>> llm_service = LLMService(model_name="llama3.2")
            >>> orchestrator = RAGOrchestrator(doc_service, llm_service)
        """
        self.doc_retrieval_service = doc_retrieval_service
        self.llm_service = llm_service

        logger.info(
            "Initialized RAG orchestrator",
        )

    def query(
        self,
        query_text: str,
        history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[Any]]:
        """Generate a response using RAG.

        Args:
            query_text: The user's query
            history: Chat history (optional)

        Returns:
            Tuple containing the response and the retrieved documents
        """
        try:
            # Step 1: Retrieve relevant documents
            retrieved_docs = self.doc_retrieval_service.retrieve_documents(
                query_text,
            )

            # Step 2: Format documents as context for LLM
            context_text = self.doc_retrieval_service.format_documents_as_context(
                retrieved_docs,
            )

            # Step 3: Create prompts
            system_prompt = load_prompt("system_prompt")
            user_prompt = load_prompt(
                "user_query",
                context=context_text,
                question=query_text,
            )

            # Step 4: Generate response using LLM service
            logger.info("Generating response with LLM")
            response = self.llm_service.generate_response(
                prompt=user_prompt,
                system_prompt=system_prompt,
                history=history,
            )

            return str(response), retrieved_docs
        except Exception:
            logger.exception("Error generating RAG response")
            return (
                "I encountered an error while processing your query. Please try again.",
                [],
            )

    def query_stream(
        self,
        query_text: str,
        history: list[dict[str, Any]] | None = None,
    ) -> tuple[Generator[str], list[Any]]:
        """Generate a streaming response using RAG.

        Args:
            query_text: The user's query
            history: Chat history (optional)

        Returns:
            Tuple containing the response generator and the retrieved documents
        """
        try:
            # Step 1: Retrieve relevant documents up front
            logger.info("Retrieving relevant documents")
            retrieved_docs = self.doc_retrieval_service.retrieve_documents(
                query_text,
            )

            # Step 2: Format documents as context for LLM
            context_text = self.doc_retrieval_service.format_documents_as_context(
                retrieved_docs,
            )

            # Step 3: Create prompts
            system_prompt = load_prompt("system_prompt")
            user_prompt = load_prompt(
                "user_query",
                context=context_text,
                question=query_text,
            )

            # Step 4: Create the streaming generator
            logger.info("Generating streaming response with LLM")

            def stream_generator() -> Generator[str]:
                llm_response_stream = self.llm_service.generate_response_stream(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    history=history,
                )
                try:
                    logger.info("Starting to consume LLM response stream")
                    # Stream the LLM response directly using yield from
                    yield from llm_response_stream

                except Exception:
                    logger.exception("Error in stream generator")
                    yield "I encountered an error while processing your query. Please try again."
                finally:
                    # Ensure proper cleanup of upstream generator
                    if hasattr(llm_response_stream, "close"):
                        llm_response_stream.close()

            return stream_generator(), retrieved_docs

        except Exception:
            logger.exception("Error in query_stream setup")

            def error_generator() -> Generator[str]:
                yield "I encountered an error while processing your query. Please try again."

            return error_generator(), []

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
