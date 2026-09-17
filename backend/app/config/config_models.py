"""Runtime models for the Tapio application service."""

from dataclasses import dataclass, field

from app.config.llm_settings import LLMSettings
from app.config.settings import (
    DEFAULT_CHROMA_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_NUM_RESULTS,
    DEFAULT_VECTORSTORE_DIR,
)


@dataclass
class RAGConfig:
    """Settings needed by the query-side RAG application.

    ``llm_provider``/``llm_model_name`` default from ``LLMSettings`` (env vars
    ``TAPIO_LLM_PROVIDER``/``TAPIO_LLM_MODEL``, see ``app.config.llm_settings``)
    rather than a fixed constant, so the LLM backend is swappable via
    configuration without a code change (#9).
    """

    collection_name: str = DEFAULT_CHROMA_COLLECTION
    persist_directory: str = DEFAULT_VECTORSTORE_DIR
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL
    llm_provider: str = field(default_factory=lambda: LLMSettings().provider)
    llm_model_name: str = field(default_factory=lambda: LLMSettings().model)
    max_tokens: int = DEFAULT_MAX_TOKENS
    num_results: int = DEFAULT_NUM_RESULTS
