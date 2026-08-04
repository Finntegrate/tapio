"""Bounded deep-crawl discovery: the only discovery path when no sitemap exists.

Discovery-only for Phase 1 - it records discovered, in-scope URLs but does
not persist rendered Markdown (that is Requirement 3/Phase 2's job).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, cast

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import (
    ContentTypeFilter,
    DomainFilter,
    FilterChain,
    URLFilter,
    URLPatternFilter,
)
from crawl4ai.models import CrawlResultContainer

from tapio_crawler.config.config_models import GapCrawlConfig, ScopeConfig
from tapio_crawler.discovery.rate_limiter import HostRateLimiter

logger = logging.getLogger(__name__)


@dataclass
class GapCrawlResult:
    """Discovered URLs from one bounded deep-crawl discovery pass."""

    urls: list[str] = field(default_factory=list)
    complete: bool = True


async def discover_via_gap_crawl(
    gap_crawl: GapCrawlConfig,
    scope: ScopeConfig,
    *,
    user_agent: str,
    rate_limiter: HostRateLimiter,
    max_concurrent: int,
) -> GapCrawlResult:
    """Run a bounded BFS crawl to discover URLs when no sitemap exists.

    Reuses ``rate_limiter``'s current delay window - shared with any robots
    or sitemap fetches already made for this host - rather than resetting
    host spacing with its own values.
    """
    if not gap_crawl.enabled or not gap_crawl.seed_urls:
        return GapCrawlResult(complete=False)

    run_config = CrawlerRunConfig(
        deep_crawl_strategy=BFSDeepCrawlStrategy(
            max_depth=gap_crawl.max_depth,
            max_pages=gap_crawl.max_pages,
            include_external=False,
            filter_chain=FilterChain(_build_filters(scope)),
        ),
        cache_mode=CacheMode.BYPASS,
        mean_delay=rate_limiter.min_delay,
        max_range=max(0.0, rate_limiter.max_delay - rate_limiter.min_delay),
        semaphore_count=max_concurrent,
        verbose=False,
    )
    browser_config = BrowserConfig(
        browser_type="chromium",
        chrome_channel="chrome",
        headless=True,
        user_agent=user_agent,
        verbose=False,
    )

    discovered: list[str] = []
    complete = True
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            await rate_limiter.wait_for_turn()
            raw_results = cast(
                "list[CrawlResultContainer]",
                await crawler.arun_many(gap_crawl.seed_urls, config=run_config),
            )
            discovered = [result.url for result in raw_results if result.success]
            complete = all(result.success for result in raw_results)
    except Exception:
        logger.exception("Gap-crawl discovery failed for %s", gap_crawl.seed_urls)
        complete = False

    return GapCrawlResult(urls=discovered, complete=complete)


def _build_filters(scope: ScopeConfig) -> list[URLFilter]:
    filters: list[URLFilter] = []
    if scope.allowed_domains:
        filters.append(DomainFilter(allowed_domains=scope.allowed_domains))
    if scope.include_url_patterns:
        filters.append(
            URLPatternFilter(patterns=cast("Any", scope.include_url_patterns)),
        )
    if scope.allowed_content_types:
        filters.append(ContentTypeFilter(allowed_types=scope.allowed_content_types))
    return filters
