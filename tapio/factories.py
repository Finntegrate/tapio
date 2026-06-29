"""Factory classes for creating complex object graphs with dependency injection.

This module provides factory classes that handle the wiring of dependencies
for the RAG system, making it easy to create properly configured service
instances without tight coupling.
"""

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings

from tapio.config.config_models import RAGConfig
from tapio.services.document_retrieval_service import DocumentRetrievalService
from tapio.services.llm_service import LLMService
from tapio.services.rag_orchestrator import RAGOrchestrator
from tapio.vectorstore.chroma_store import ChromaStore


class RAGOrchestratorFactory:
    """Factory for creating RAGOrchestrator instances with all dependencies.

    This factory handles the complete dependency graph for a RAG orchestrator,
    including embeddings, vector store, document retrieval service, and LLM
    service. It ensures all components are properly configured and wired
    together.

    Args:
        config: Configuration object containing all RAG settings

    Example:
        >>> from tapio.config.config_models import RAGConfig
        >>> config = RAGConfig(collection_name="my_docs")
        >>> factory = RAGOrchestratorFactory(config)
        >>> orchestrator = factory.create_orchestrator()
    """

    def __init__(self, config: RAGConfig) -> None:
        """Initialize the factory with configuration.

        Args:
            config: RAGConfig instance containing all configuration parameters
        """
        self.config = config

    def create_embeddings(self) -> HuggingFaceEmbeddings:
        """Create embeddings instance.

        Returns:
            Configured HuggingFaceEmbeddings instance
        """
        return HuggingFaceEmbeddings(model_name=self.config.embedding_model_name)

    def create_chroma_store(self, embeddings: Embeddings | None = None) -> ChromaStore:
        """Create ChromaDB vector store.

        Args:
            embeddings: Optional embeddings instance. If None, creates new instance.

        Returns:
            Configured ChromaStore instance
        """
        if embeddings is None:
            embeddings = self.create_embeddings()

        return ChromaStore(
            collection_name=self.config.collection_name,
            embeddings=embeddings,
            persist_directory=self.config.persist_directory,
        )

    def create_document_retrieval_service(self, chroma_store: ChromaStore | None = None) -> DocumentRetrievalService:
        """Create document retrieval service.

        Args:
            chroma_store: Optional ChromaStore instance. If None, creates new instance.

        Returns:
            Configured DocumentRetrievalService instance
        """
        if chroma_store is None:
            chroma_store = self.create_chroma_store()

        return DocumentRetrievalService(
            vector_store=chroma_store,
            num_results=self.config.num_results,
        )

    def create_llm_service(self) -> LLMService:
        """Create LLM service.

        Returns:
            Configured LLMService instance
        """
        return LLMService(
            model_name=self.config.llm_model_name,
            max_tokens=self.config.max_tokens,
        )

    def create_orchestrator(self) -> RAGOrchestrator:
        """Create fully configured RAG orchestrator.

        This is the main factory method that creates the complete RAG system
        with all dependencies properly wired together.

        Returns:
            Configured RAGOrchestrator instance ready to use

        Example:
            >>> factory = RAGOrchestratorFactory(RAGConfig())
            >>> orchestrator = factory.create_orchestrator()
            >>> response, docs = orchestrator.query("What is the processing time?")
        """
        # Create shared embeddings instance
        embeddings = self.create_embeddings()

        # Create vector store with embeddings
        chroma_store = self.create_chroma_store(embeddings)

        # Create services
        doc_service = self.create_document_retrieval_service(chroma_store)
        llm_service = self.create_llm_service()

        # Create and return orchestrator
        return RAGOrchestrator(
            doc_retrieval_service=doc_service,
            llm_service=llm_service,
        )
