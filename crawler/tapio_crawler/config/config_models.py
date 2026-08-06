"""Configuration models for Crawl4AI collection jobs."""

from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, model_validator

# Identifies Tapio to source operators instead of a spoofed browser string.
DEFAULT_USER_AGENT = (
    "TapioBot/1.0 (+https://github.com/Finntegrate/tapio; "
    "nonprofit immigration-guidance assistant; contact via repository)"
)


class MarkdownConfig(BaseModel):
    """Options forwarded to Crawl4AI's html2text-compatible generator."""

    ignore_links: bool = False
    body_width: Annotated[int, Field(ge=0)] = 0
    protect_links: bool = True
    unicode_snob: bool = True
    ignore_images: bool = False
    ignore_tables: bool = False


class PolitenessConfig(BaseModel):
    """Identification and rate-limiting posture for one source."""

    respect_crawl_delay: bool = True
    user_agent: str = DEFAULT_USER_AGENT


class DiscoveryConfig(BaseModel):
    """How a source's URL inventory is discovered."""

    source: Literal["sitemap", "none"] = "none"
    # Empty: read ``Sitemap:`` entries from the source's robots.txt instead.
    sitemap_urls: list[str] = Field(default_factory=list)
    # Whether sitemap lastmod may trigger a re-render (Requirement 5). Stays
    # False until a source's lastmod is empirically shown to correlate with
    # real content changes, per docs/specs/crawler-improvements.md.
    trust_lastmod: bool = False


class ScopeConfig(BaseModel):
    """Domain and path rules bounding a source's eligible URLs."""

    allowed_domains: list[str] = Field(default_factory=list)
    exclude_url_patterns: list[str] = Field(default_factory=list)
    allowed_content_types: list[str] = Field(default_factory=lambda: ["text/html"])


class GapCrawlConfig(BaseModel):
    """Bounded deep-crawl discovery settings for one source."""

    enabled: bool = False
    seed_urls: list[str] = Field(default_factory=list)
    strategy: Literal["bfs"] = "bfs"
    max_depth: Annotated[int, Field(ge=0, le=10)] = 2
    max_pages: Annotated[int, Field(ge=1, le=1_000)] = 100


class RefreshConfig(BaseModel):
    """Per-document refresh scheduling and coverage targets for one source.

    Attributes:
        unchanged_audit_days: How many days a rendered document may go
            without a fresh check before it becomes due again for a
            scheduled audit, even without a signal that it changed.
        inactive_grace_cycles: How many consecutive discovery runs a
            previously eligible URL may go missing before it is treated as
            removed from the source, rather than a transient omission.
        coverage_target_percent: The share of eligible URLs, 0-100, that
            should have a successful current document before a render run
            is considered to have met its coverage target; used only to
            flag a shortfall in run output, not to gate anything.
    """

    unchanged_audit_days: Annotated[int, Field(ge=1)] = 90
    inactive_grace_cycles: Annotated[int, Field(ge=1)] = 2
    coverage_target_percent: Annotated[float, Field(ge=0.0, le=100.0)] = 95.0


class CrawlerConfig(BaseModel):
    """Bounded, polite settings for a site's Crawl4AI job."""

    page_timeout: Annotated[int, Field(ge=1, le=120)] = 30
    min_delay: Annotated[float, Field(ge=0.0)] = 1.0
    max_delay: Annotated[float, Field(ge=0.0)] = 3.0
    max_concurrent: Annotated[int, Field(ge=1, le=20)] = 3
    minimum_content_length: Annotated[int, Field(ge=1)] = 100
    word_count_threshold: Annotated[int, Field(ge=0)] = 20
    css_selector: str | None = None
    target_elements: list[str] = Field(default_factory=list)
    remove_consent_popups: bool = False
    remove_overlay_elements: bool = False
    markdown_config: MarkdownConfig = Field(default_factory=MarkdownConfig)
    robots_policy: Literal["require"] = "require"
    politeness: PolitenessConfig = Field(default_factory=PolitenessConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    gap_crawl: GapCrawlConfig = Field(default_factory=GapCrawlConfig)
    refresh: RefreshConfig = Field(default_factory=RefreshConfig)

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
        """Return the hostname used for output organisation.

        :raises ValueError: If ``base_url`` does not contain a valid hostname.
        """
        host = urlparse(str(self.base_url)).hostname
        if not host:
            msg = f"Invalid base_url: {self.base_url!s}"
            raise ValueError(msg)
        return host


class SiteConfigRegistry(BaseModel):
    """Registry of all configured source sites."""

    sites: dict[str, SiteConfig]
