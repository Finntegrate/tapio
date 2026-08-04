"""Dispatches sitemap or gap-crawl discovery for one site and records the
resulting URL inventory in the manifest.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from tapio_crawler.config.config_models import CrawlerConfig, SiteConfig
from tapio_crawler.discovery.gap_crawl import discover_via_gap_crawl
from tapio_crawler.discovery.rate_limiter import (
    HostRateLimiter,
    resolve_effective_delay,
)
from tapio_crawler.discovery.robots import RobotsRules, fetch_robots_rules
from tapio_crawler.discovery.scope import evaluate_scope
from tapio_crawler.discovery.sitemap import discover_sitemap_urls
from tapio_crawler.manifest.models import DiscoverySource, ManifestRecord, ScopeStatus
from tapio_crawler.manifest.normalize import canonicalize_url
from tapio_crawler.manifest.store import ManifestStore

logger = logging.getLogger(__name__)

_SCOPE_REASON_STATUS: dict[str, ScopeStatus] = {
    "domain_not_allowed": "out_of_scope",
    "not_in_include_patterns": "out_of_scope",
    "excluded_by_pattern": "excluded",
}


@dataclass
class DiscoveryRunSummary:
    """Counts describing one discovery run, for the run's report/log line."""

    run_id: str
    site_name: str
    discovered: int = 0
    eligible: int = 0
    excluded_by_reason: dict[str, int] = field(default_factory=dict)
    child_sitemaps_fetched: int = 0
    complete: bool = True


class MisconfiguredDiscoveryError(Exception):
    """Raised when a site has no way to discover URLs at all."""


class DiscoveryRunner:
    """Runs one discovery pass for a site and upserts results into the manifest."""

    def __init__(self, manifest_store: ManifestStore) -> None:
        self._manifest_store = manifest_store

    async def run(self, site_name: str, site_config: SiteConfig) -> DiscoveryRunSummary:
        """Discover URLs for ``site_name`` and record them in the manifest."""
        run_id = str(uuid.uuid4())
        summary = DiscoveryRunSummary(run_id=run_id, site_name=site_name)
        config = site_config.crawler_config
        _require_discovery_source(site_name, config)

        # Shared across robots, sitemap, and gap-crawl requests to this host so a
        # Crawl-delay floor or Retry-After suspension applies uniformly.
        rate_limiter = HostRateLimiter(
            min_delay=config.min_delay, max_delay=config.max_delay
        )
        base_url = str(site_config.base_url).rstrip("/")
        robots = await fetch_robots_rules(
            base_url,
            config.politeness.user_agent,
            rate_limiter=rate_limiter,
        )
        if not robots.reachable and config.robots_policy == "require":
            summary.complete = False
            logger.warning(
                "robots.txt unreachable for %s; marking run incomplete", site_name
            )
            return summary

        effective_delay = resolve_effective_delay(
            configured_min_delay=config.min_delay,
            configured_max_delay=config.max_delay,
            crawl_delay=robots.crawl_delay
            if config.politeness.respect_crawl_delay
            else None,
        )
        rate_limiter.min_delay = effective_delay.min_delay
        rate_limiter.max_delay = effective_delay.max_delay

        discovered_urls, lastmod_by_url, source_tag = await self._discover_urls(
            config,
            robots,
            rate_limiter,
            summary,
        )
        self._persist_discovered_urls(
            site_name,
            config,
            discovered_urls,
            lastmod_by_url,
            source_tag,
            summary,
        )
        return summary

    async def _discover_urls(
        self,
        config: CrawlerConfig,
        robots: RobotsRules,
        rate_limiter: HostRateLimiter,
        summary: DiscoveryRunSummary,
    ) -> tuple[list[str], dict[str, datetime | None], DiscoverySource]:
        """Dispatch to sitemap or gap-crawl discovery and update run counts."""
        if config.discovery.source == "sitemap":
            sitemap_urls = config.discovery.sitemap_urls or robots.sitemap_urls
            async with httpx.AsyncClient() as client:
                sitemap_result = await discover_sitemap_urls(
                    sitemap_urls,
                    client=client,
                    rate_limiter=rate_limiter,
                    user_agent=config.politeness.user_agent,
                    allowed_hosts=config.scope.allowed_domains or None,
                )
            summary.child_sitemaps_fetched = sitemap_result.child_sitemaps_fetched
            summary.complete = sitemap_result.complete
            discovered_urls = [entry.url for entry in sitemap_result.urls]
            lastmod_by_url = {entry.url: entry.lastmod for entry in sitemap_result.urls}
            return discovered_urls, lastmod_by_url, "sitemap"

        gap_result = await discover_via_gap_crawl(
            config.gap_crawl,
            config.scope,
            user_agent=config.politeness.user_agent,
            rate_limiter=rate_limiter,
            max_concurrent=config.max_concurrent,
        )
        summary.complete = gap_result.complete
        return gap_result.urls, {}, "deep_crawl"

    def _persist_discovered_urls(
        self,
        site_name: str,
        config: CrawlerConfig,
        discovered_urls: list[str],
        lastmod_by_url: dict[str, datetime | None],
        source_tag: DiscoverySource,
        summary: DiscoveryRunSummary,
    ) -> None:
        """Score every discovered URL against scope and upsert it into the manifest."""
        summary.discovered = len(discovered_urls)
        now = datetime.now(UTC)
        for url in discovered_urls:
            decision = evaluate_scope(url, config.scope)
            if decision.eligible:
                summary.eligible += 1
            else:
                reason = decision.reason or "unknown"
                summary.excluded_by_reason[reason] = (
                    summary.excluded_by_reason.get(reason, 0) + 1
                )

            record = ManifestRecord(
                site_name=site_name,
                source_url=url,
                canonical_url=canonicalize_url(url),
                discovery_source={source_tag},
                sitemap_lastmod=lastmod_by_url.get(url),
                first_seen_at=now,
                last_seen_at=now,
                scope_status=(
                    "eligible"
                    if decision.eligible
                    else _SCOPE_REASON_STATUS.get(decision.reason or "", "excluded")
                ),
                scope_reason=decision.reason,
            )
            self._manifest_store.upsert(record)


def _require_discovery_source(site_name: str, config: CrawlerConfig) -> None:
    """Raise if a site has neither sitemap nor gap-crawl discovery configured."""
    if config.discovery.source == "none" and not config.gap_crawl.enabled:
        msg = (
            f"{site_name}: discovery.source is 'none' but gap_crawl is not "
            "enabled; the site has no way to discover URLs"
        )
        raise MisconfiguredDiscoveryError(msg)
