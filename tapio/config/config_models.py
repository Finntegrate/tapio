"""Configuration models for the Tapio application.

This module contains Pydantic models that define the configuration for
site-specific crawling via the Cloudflare /crawl API and the RAG system.
"""

from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl

from tapio.config.settings import (
    DEFAULT_CHROMA_COLLECTION,
    DEFAULT_DIRS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_NUM_RESULTS,
)


class CrawlerConfig(BaseModel):
    """Crawler settings mapped 1:1 to the Cloudflare /crawl API."""

    max_depth: Annotated[
        int,
        Field(ge=1, le=10, description="Maximum crawling depth from starting URLs"),
    ] = 1
    limit: Annotated[
        int,
        Field(ge=1, le=100_000, description="Max pages to crawl (Cloudflare)"),
    ] = 100
    render: bool = Field(
        default=True,
        description="Enable JavaScript rendering (Cloudflare)",
    )
    source: Literal["all", "sitemaps", "links"] = Field(
        default="all",
        description='Crawl source: "all", "sitemaps", or "links" (Cloudflare)',
    )


class SiteConfig(BaseModel):
    """Configuration for a single site."""

    base_url: HttpUrl
    description: str | None = None
    crawler_config: CrawlerConfig = Field(default_factory=CrawlerConfig)

    @property
    def base_dir(self) -> str:
        """Extract the domain from base_url to use as directory name."""
        url_str = str(self.base_url)
        parsed = urlparse(url_str)
        host = parsed.hostname
        if not host:
            msg = f"Invalid base_url: {url_str}"
            raise ValueError(msg)
        return host


class ParserConfigRegistry(BaseModel):
    """Registry holding all site configurations loaded from YAML."""

    sites: dict[str, SiteConfig]


class RAGConfig(BaseModel):
    """Configuration for the RAG system."""

    embedding_model_name: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        description="Name of the HuggingFace embedding model to use",
    )
    llm_model_name: str = Field(
        default=DEFAULT_LLM_MODEL,
        description="Name of the Ollama LLM to use",
    )
    llm_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for the Ollama server",
    )
    persist_directory: str = Field(
        default=DEFAULT_DIRS["CHROMA_DIR"],
        description="Directory where the vector store is persisted",
    )
    collection_name: str = Field(
        default=DEFAULT_CHROMA_COLLECTION,
        description="Name of the Chroma collection to use",
    )
    max_tokens: int = Field(
        default=DEFAULT_MAX_TOKENS,
        description="Maximum number of tokens for LLM responses",
    )
    num_results: int = Field(
        default=DEFAULT_NUM_RESULTS,
        description="Number of results to retrieve from the vector store",
    )