"""Configuration models for HTML content parsers.

This module contains Pydantic models that define the configuration for
site-specific HTML parsing, including content selectors and HTML-to-Markdown
conversion settings.
"""

from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl

from tapio.config.settings import (
    DEFAULT_CHROMA_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_NUM_RESULTS,
)


class HtmlToMarkdownConfig(BaseModel):
    """Configuration settings for HTML to Markdown conversion.

    Customizes how HTML elements are converted to Markdown. These settings are
    mapped to html2text options.
    """

    ignore_links: bool = False
    body_width: int = 0  # Don't wrap text
    protect_links: bool = True  # Don't wrap links
    unicode_snob: bool = True  # Use Unicode instead of ASCII
    ignore_images: bool = False  # Include images
    ignore_tables: bool = False  # Include tables


class CrawlerConfig(BaseModel):
    """Configuration settings for web crawling behavior.

    Defines crawler-specific settings such as rate limiting, concurrency limits,
    and other behavioral parameters to prevent overwhelming target servers.
    """

    delay_between_requests: Annotated[
        float,
        Field(ge=0.0, description="Delay between requests in seconds to avoid rate limiting"),
    ] = 1.0
    max_concurrent: Annotated[int, Field(ge=1, le=50, description="Maximum number of concurrent requests")] = 5
    max_depth: Annotated[int, Field(ge=1, le=10, description="Maximum crawling depth from starting URLs")] = 1


class ParserConfig(BaseModel):
    """Configuration settings for HTML content parsing.

    Defines parser-specific settings such as content selectors, title selectors,
    and HTML-to-Markdown conversion options.
    """

    title_selector: str = "//title"
    content_selectors: list[str] = Field(
        default_factory=lambda: ["//main", "//article", "//body"],
        description="Priority-ordered list of XPath selectors to find content",
    )
    fallback_to_body: bool = True
    markdown_config: HtmlToMarkdownConfig = Field(default_factory=HtmlToMarkdownConfig)

    def get_content_selector(self, tree: Any) -> Any | None:
        """Find the first matching content element using the configured selectors.

        Args:
            tree: An lxml HTML tree to search

        Returns:
            The first matching element or None if no match is found
        """
        for selector in self.content_selectors:
            elements = tree.xpath(selector)
            if elements:
                return elements[0]
        return None


class SiteConfig(BaseModel):
    """Configuration for site-specific operations.

    Defines the overall configuration for a site, including base URL, description,
    and references to both parser and crawler configurations.
    """

    base_url: HttpUrl
    description: str | None = None
    parser_config: ParserConfig = Field(default_factory=ParserConfig)
    crawler_config: CrawlerConfig = Field(default_factory=CrawlerConfig)

    @property
    def base_dir(self) -> str:
        """Derive base directory from base_url.

        Extracts the domain from the base URL to use as the directory name.

        Returns:
            Domain name without protocol prefix (e.g., 'migri.fi')
        """
        url_str = str(self.base_url)
        parsed = urlparse(url_str)
        # Use hostname to strip any port, and ensure a non-empty result
        host = parsed.hostname
        if not host:
            msg = f"Invalid base_url: {url_str!r}"
            raise ValueError(msg)
        return host

    def get_content_selector(self, tree: Any) -> Any | None:
        """Find the first matching content element using the configured selectors.

        Args:
            tree: An lxml HTML tree to search

        Returns:
            The first matching element or None if no match is found
        """
        return self.parser_config.get_content_selector(tree)


class ParserConfigRegistry(BaseModel):
    """Registry of all site parser configurations."""

    sites: dict[str, SiteConfig]


@dataclass
class RAGConfig:
    """Configuration for RAG (Retrieval Augmented Generation) system.

    Groups all configuration parameters for the RAG orchestrator and its
    dependencies, including vector store settings, embedding model, and
    LLM configuration.

    Args:
        collection_name: Name of the ChromaDB collection
        persist_directory: Directory path for ChromaDB persistence
        embedding_model_name: Name of the HuggingFace embedding model
        llm_model_name: Name of the Ollama LLM model
        max_tokens: Maximum tokens for LLM generation
        num_results: Number of documents to retrieve for context

    Example:
        >>> config = RAGConfig(
        ...     collection_name="my_docs",
        ...     llm_model_name="llama3.2:latest"
        ... )
    """

    collection_name: str = DEFAULT_CHROMA_COLLECTION
    persist_directory: str = "chroma_db"
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL
    llm_model_name: str = DEFAULT_LLM_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    num_results: int = DEFAULT_NUM_RESULTS
