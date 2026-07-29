"""Document retrieval service for the Tapio Assistant."""

import logging
from typing import Any

from langsmith import traceable

from tapio.core.tracing import trace_retrieval_metadata
from tapio.vectorstore.chroma_store import ChromaStore

# Configure logging
logger = logging.getLogger(__name__)


class DocumentRetrievalService:
    """Service for retrieving relevant documents from the vector store.

    This service handles document retrieval from a vector store and formats
    the results for use in RAG workflows. The vector store is injected to
    enable testing and allow reuse of existing store instances.
    """

    def __init__(
        self,
        vector_store: ChromaStore,
        num_results: int = 5,
    ) -> None:
        """Initialize the document retrieval service.

        Args:
            vector_store: ChromaStore instance for document retrieval
            num_results: Number of documents to retrieve from the vector store

        Example:
            >>> from tapio.vectorstore.chroma_store import ChromaStore
            >>> from langchain_huggingface import HuggingFaceEmbeddings
            >>>
            >>> embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            >>> store = ChromaStore("my_docs", embeddings)
            >>> service = DocumentRetrievalService(vector_store=store, num_results=3)
        """
        self.num_results = num_results
        self.vector_store = vector_store

        logger.info(
            "Initialized document retrieval service",
        )

    @traceable(run_type="retriever", name="Document Retrieval")
    def retrieve_documents(self, query_text: str) -> list[Any]:
        """Retrieve relevant documents for the given query.

        Args:
            query_text: The user's query

        Returns:
            List of retrieved documents
        """
        try:
            # Avoid logging raw query text, which may contain personal information
            logger.info("Retrieving documents for query (%d chars)", len(query_text))
            retrieved_docs = self.vector_store.query(
                query_text=query_text,
                n_results=self.num_results,
            )
            logger.info("Retrieved %d documents", len(retrieved_docs))

            # Log retrieved document metadata and content previews
            for i, d in enumerate(retrieved_docs):
                meta = d.metadata if hasattr(d, "metadata") else {}
                preview = (getattr(d, "page_content", "") or "")[:200]
                logger.info(
                    "Doc %d: source_id=%s title=%s chunk=%s/%s url=%s preview=%.200s",
                    i + 1,
                    meta.get("source_id", "?"),
                    meta.get("title", "?"),
                    meta.get("chunk_index", "?"),
                    meta.get("total_chunks", "?"),
                    meta.get("source_url") or meta.get("url", "?"),
                    preview.replace("\n", " "),
                )

            # Trace structured metadata (chunk IDs, source URLs, titles, etc.)
            trace_retrieval_metadata(retrieved_docs)
        except Exception:
            logger.exception("Error retrieving documents")
            return []
        else:
            return retrieved_docs

    def format_documents_as_context(self, documents: list[Any]) -> str:
        """Format retrieved documents as context for LLM input.

        Args:
            documents: List of retrieved documents

        Returns:
            Formatted string containing document content for LLM context
        """
        if not documents:
            return ""

        context_docs = [doc.page_content for doc in documents if hasattr(doc, "page_content")]

        return "\n\n".join(context_docs)

    def format_documents_for_display(self, documents: list[Any]) -> str:
        """Format retrieved documents for user display.

        Args:
            documents: List of retrieved documents

        Returns:
            Formatted string containing document information for display
        """
        if not documents:
            return "No relevant documents found."

        formatted_docs = []
        for i, doc in enumerate(documents):
            # Extract metadata
            metadata = doc.metadata if hasattr(doc, "metadata") else {}
            source = metadata.get(
                "source_url",
                metadata.get("url", "Unknown source"),
            )
            title = metadata.get("title", f"Document {i + 1}")
            chunk_index = metadata.get("chunk_index")
            total_chunks = metadata.get("total_chunks")
            source_id = metadata.get("source_id")

            # Build metadata badges
            badges = []
            if source_id:
                badges.append(f"ID: `{source_id}`")
            if chunk_index is not None and total_chunks is not None:
                badges.append(f"Chunk {chunk_index + 1}/{total_chunks}")

            # Format the document with metadata
            doc_content = (
                doc.page_content
                if hasattr(
                    doc,
                    "page_content",
                )
                else str(doc)
            )
            header = f"### {title}"
            if badges:
                header += f"\n*{', '.join(badges)}*"
            formatted_doc = f"{header}\n**Source**: {source}\n\n{doc_content}\n\n"
            formatted_docs.append(formatted_doc)

        return "\n".join(formatted_docs)
