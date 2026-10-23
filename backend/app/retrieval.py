"""Read-only vector-store client owned by the Tapio application."""

import logging
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.config.settings import DEFAULT_VECTORSTORE_DIR

logger = logging.getLogger(__name__)


class ChromaRetriever:
    """Query-side adapter for a vector collection populated by ``tapio-ingest``."""

    def __init__(
        self,
        collection_name: str,
        embeddings: Embeddings,
        persist_directory: str = DEFAULT_VECTORSTORE_DIR,
    ) -> None:
        """Connect to the collection produced by the ingestion service.

        Args:
            collection_name: Name of the collection to query.
            embeddings: Embedding function used for similarity searches.
            persist_directory: Shared directory containing the Chroma collection.

        Returns:
            None.
        """
        self.vector_db = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_directory,
        )

    def query(self, query_text: str, n_results: int = 5, *, raise_on_error: bool = False) -> list[Document]:
        """Return the nearest documents for a user query.

        Args:
            query_text: The text to search for.
            n_results: Maximum number of documents to return.
            raise_on_error: If False (the default, used by the live chat
                path), a vector-store failure is logged and treated the same
                as a genuine no-results query, so a single user turn never
                crashes on an infrastructure hiccup. Callers that need to
                tell "no results" apart from "the store is broken" — such as
                the offline evaluation scripts — should pass True.
        """
        try:
            results = self.vector_db.similarity_search(query=query_text, k=n_results)
        except Exception:
            logger.exception("Failed to query vector store")
            if raise_on_error:
                raise
            return []

        for document in results:
            self._add_citation(document)
        return results

    @staticmethod
    def _add_citation(document: Any) -> None:
        if not hasattr(document, "metadata"):
            return
        if "source_url" in document.metadata:
            document.metadata["citation_url"] = document.metadata["source_url"]
        elif "url" in document.metadata:
            document.metadata["citation_url"] = document.metadata["url"]
