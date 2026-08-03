"""Configuration models for Crawl4AI collection jobs."""

from typing import Annotated
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, model_validator


class MarkdownConfig(BaseModel):
    """Options forwarded to Crawl4AI's html2text-compatible generator."""

    ignore_links: bool = False
    body_width: Annotated[int, Field(ge=0)] = 0
    protect_links: bool = True
    unicode_snob: bool = True
    ignore_images: bool = False
    ignore_tables: bool = False


class CrawlerConfig(BaseModel):
    """Bounded, polite settings for a site's Crawl4AI job."""

    max_depth: Annotated[int, Field(ge=0, le=10)] = 1
    max_pages: Annotated[int, Field(ge=1, le=1_000)] = 50
    page_timeout: Annotated[int, Field(ge=1, le=120)] = 30
    min_delay: Annotated[float, Field(ge=0.0)] = 1.0
    max_delay: Annotated[float, Field(ge=0.0)] = 3.0
    max_concurrent: Annotated[int, Field(ge=1, le=20)] = 3
    minimum_content_length: Annotated[int, Field(ge=1)] = 100
    css_selector: str | None = None
    target_elements: list[str] = Field(default_factory=list)
    remove_consent_popups: bool = False
    remove_overlay_elements: bool = False
    markdown_config: MarkdownConfig = Field(default_factory=MarkdownConfig)

    @model_validator(mode="after")
    def validate_delay_range(self) -> CrawlerConfig:
        """Require a valid jitter range for Crawl4AI's rate limiter."""
        if self.min_delay > self.max_delay:
            msg = "min_delay must not be greater than max_delay"
            raise ValueError(msg)
        return self


class SiteConfig(BaseModel):
    """Configuration for one source site and its Crawl4AI job."""

    base_url: HttpUrl
    description: str | None = None
    crawler_config: CrawlerConfig = Field(default_factory=CrawlerConfig)

    @property
    def base_dir(self) -> str:
        """Return the hostname used for output organisation."""
        host = urlparse(str(self.base_url)).hostname
        if not host:
            msg = f"Invalid base_url: {self.base_url!s}"
            raise ValueError(msg)
        return host


class SiteConfigRegistry(BaseModel):
    """Registry of all configured source sites."""

    sites: dict[str, SiteConfig]
