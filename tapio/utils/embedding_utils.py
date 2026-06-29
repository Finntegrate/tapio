"""Utilities for generating embeddings using LangChain."""

import logging
from typing import cast

from langchain_community.embeddings import (  # type: ignore[import-not-found]
    SentenceTransformerEmbeddings,
)

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings using LangChain's SentenceTransformerEmbeddings."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize the embedding generator.

        Args:
            model_name: Name of the embedding model to use
        """
        self.model_name = model_name
        self.embedding_model = SentenceTransformerEmbeddings(model_name=model_name)
        logger.info("Initialized embedding model: %s", model_name)

    def generate(self, text: str) -> list[float] | None:
        """Generate an embedding for a piece of text.

        Args:
            text: Text to generate an embedding for

        Returns:
            List of floats representing the embedding, or None if generation fails
        """
        try:
            # LangChain's embed_query returns a single embedding vector
            embedding = self.embedding_model.embed_query(text)
        except Exception:
            logger.exception("Error generating embedding")
            return None
        else:
            return embedding

    def generate_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to generate embeddings for

        Returns:
            List of embeddings, with None for any texts that failed
        """
        try:
            # LangChain's embed_documents returns a list of embedding vectors
            embeddings = self.embedding_model.embed_documents(texts)

            # Cast the return type to match the expected signature
            # This is safe because we know embeddings is a list[list[float]]
            # which is a subtype of list[list[float] | None]
            return cast("list[list[float] | None]", embeddings)
        except Exception:
            logger.exception("Error generating batch embeddings")
            # Return a list of Nones with the same length as the input
            return [None for _ in texts]
