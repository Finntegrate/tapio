"""Runtime models for the Tapio application service."""

from dataclasses import dataclass

from tapio_backend.config.settings import (
    DEFAULT_CHROMA_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_NUM_RESULTS,
    DEFAULT_VECTORSTORE_DIR,
)


@dataclass
class RAGConfig:
    """Settings needed by the query-side RAG application."""

    collection_name: str = DEFAULT_CHROMA_COLLECTION
    persist_directory: str = DEFAULT_VECTORSTORE_DIR
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL
    llm_model_name: str = DEFAULT_LLM_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    num_results: int = DEFAULT_NUM_RESULTS
