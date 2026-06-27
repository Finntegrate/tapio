"""ChromaDB vector store abstraction using LangChain."""

import logging
from typing import Any

from langchain_chroma import Chroma  # type: ignore[import-not-found]
from langchain_core.documents import Document  # type: ignore[import-not-found]
from langchain_core.embeddings import Embeddings  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


class ChromaStore:
    """LangChain-based ChromaDB vector store abstraction.

    This class wraps LangChain's Chroma implementation with a simpler interface.
    Dependencies are injected to allow for testing and configuration flexibility.
    """

    def __init__(
        self,
        collection_name: str,
        embeddings: Embeddings,
        persist_directory: str = "chroma_db",
    ) -> None:
        """Initialize the ChromaDB vector store.

        Args:
            collection_name: Name of the ChromaDB collection
            embeddings: Embeddings instance (e.g., HuggingFaceEmbeddings)
            persist_directory: Directory to persist the ChromaDB database

        Example:
            >>> from langchain_huggingface import HuggingFaceEmbeddings
            >>> embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            >>> store = ChromaStore(
            ...     collection_name="my_docs",
            ...     embeddings=embeddings,
            ...     persist_directory="./chroma_db"
            ... )
        """
        self.embeddings = embeddings

        # Initialize the vector store
        self.vector_db = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=persist_directory,
        )

        logger.debug("Initialized ChromaStore with collection: %s", collection_name)

    def add_document(
        self,
        document_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a document to the vector store.

        This method is maintained for backward compatibility but uses the langchain Chroma
        implementation internally.

        Args:
            document_id: Unique identifier for the document
            metadata: Document metadata
        """
        try:
            # Extract content from metadata if available
            document_text = metadata.get("content", "") if metadata else ""

            # If content is missing from metadata but available elsewhere, try to find it
            if not document_text and metadata is not None:
                # Look for content in other common field names
                for field in ["text", "body", "page_content", "full_text"]:
                    if metadata is not None and field in metadata:
                        document_text = metadata[field]
                        break

            # Ensure we have some text content
            if not document_text:
                logger.warning("No content found for document %s", document_id)
                document_text = f"Empty document: {document_id}"

            # Create document dictionary with IDs
            # Note: LangChain's Chroma will compute embeddings automatically if not provided
            self.vector_db.add_texts(
                texts=[document_text],
                metadatas=[metadata] if metadata is not None else None,
                ids=[document_id],
            )

            logger.debug("Added document %s to vector store", document_id)

        except Exception:
            logger.exception("Failed to add document %s", document_id)
            raise

    def query(self, query_text: str, n_results: int = 5) -> list[Document]:
        """Query the vector store by text.

        Args:
            query_text: Text to search for
            n_results: Number of results to return

        Returns:
            List of documents most similar to the query
        """
        try:
            results = self.vector_db.similarity_search(query=query_text, k=n_results)

            # Enhance results with citation information
            for doc in results:
                self._enhance_document_with_citation(doc)
        except Exception:
            logger.exception("Failed to query vector store")
            return []
        else:
            return results

    def query_with_embedding(
        self,
        embedding: list[float],
        n_results: int = 5,
    ) -> list[tuple[Document, float]]:
        """Query the vector store by embedding.

        Args:
            embedding: Embedding vector to search with
            n_results: Number of results to return

        Returns:
            List of (document, relevance score) pairs most similar to the query
        """
        try:
            results = self.vector_db.similarity_search_by_vector_with_relevance_scores(
                embedding,
                k=n_results,
            )

            # Enhance results with citation information
            for doc, _score in results:
                self._enhance_document_with_citation(doc)
        except Exception:
            logger.exception("Failed to query vector store with embedding")
            return []
        else:
            return results

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Get a document by ID.

        Args:
            document_id: ID of the document to retrieve

        Returns:
            The document if found
        """
        try:
            result = self.vector_db.get(
                ids=[document_id],
                include=["documents", "metadatas"],
            )

            # Add citation information
            if result and "metadatas" in result and result["metadatas"]:
                for metadata in result["metadatas"]:
                    if isinstance(metadata, dict):
                        if "source_url" in metadata:
                            metadata["citation_url"] = metadata["source_url"]
                        elif "url" in metadata:
                            metadata["citation_url"] = metadata["url"]

        except Exception:
            logger.exception("Failed to get document %s", document_id)
            return None
        else:
            return result

    def _enhance_document_with_citation(self, doc: Any) -> None:
        """Enhance a document with citation information.

        Args:
            doc: LangChain document object to enhance
        """
        if not hasattr(doc, "metadata"):
            return

        # Add citation_url for convenient access in RAG applications
        if "source_url" in doc.metadata:
            doc.metadata["citation_url"] = doc.metadata["source_url"]
        elif "url" in doc.metadata:
            doc.metadata["citation_url"] = doc.metadata["url"]
