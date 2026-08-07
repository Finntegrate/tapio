"""Discovery run orchestration.

Dispatches sitemap or gap-crawl discovery for one site and records the
resulting URL inventory in the manifest.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

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
    "excluded_by_pattern": "excluded",
}

# Bumped whenever the fields hashed below change, so a stored fingerprint
# from an older version of this function never falsely matches.
_CONFIG_FINGERPRINT_VERSION = "v1"


def _config_fingerprint(config: CrawlerConfig, base_url: str) -> str:
    """Hash the discovery/scope settings a cached run's counts depend on.

    Used to invalidate a ``discovery.cache_ttl_hours`` cache hit when
    ``sitemap_urls``, the site's scope rules, or its base URL change, even
    within the TTL window that would otherwise still consider the cache
    fresh.

    Args:
        config: The site's crawler configuration.
        base_url: The site's configured base URL, normalized (trailing
            slash stripped) before hashing so equivalent URLs fingerprint
            the same way.

    Returns:
        A version-prefixed hex digest, for example ``"v1:<hex>"``.
    """
    payload = {
        "base_url": base_url.rstrip("/"),
        "discovery_source": config.discovery.source,
        "sitemap_urls": config.discovery.sitemap_urls,
        "allowed_domains": config.scope.allowed_domains,
        "exclude_url_patterns": config.scope.exclude_url_patterns,
        "allowed_content_types": config.scope.allowed_content_types,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"{_CONFIG_FINGERPRINT_VERSION}:{digest}"


@dataclass
class DiscoveryRunSummary:
    """Counts describing one discovery run, for the run's report/log line.

    Attributes:
        run_id: Unique identifier for this discovery run.
        site_name: Name of the configured source site.
        discovered: Total number of URLs discovered, before scope filtering.
        eligible: Number of discovered URLs that are eligible for collection.
        excluded_by_reason: Count of excluded URLs, keyed by exclusion reason.
        child_sitemaps_fetched: Number of child sitemaps fetched when the
            source was a sitemap index.
        complete: Whether the run finished without a fatal interruption
            (for example, an unreachable robots.txt or a failed fetch).
        robots_txt_url: The robots.txt URL this run fetched.
        sitemap_urls: The top-level sitemap URLs this run fetched from,
            empty for a gap-crawl-only source.
        cached: Whether this summary was rebuilt from a prior discovery
            run's manifest state, per ``discovery.cache_ttl_hours``, instead
            of re-fetching robots.txt and the sitemap.
    """

    run_id: str
    site_name: str
    discovered: int = 0
    eligible: int = 0
    excluded_by_reason: dict[str, int] = field(default_factory=dict)
    child_sitemaps_fetched: int = 0
    complete: bool = True
    robots_txt_url: str = ""
    sitemap_urls: list[str] = field(default_factory=list)
    cached: bool = False


class MisconfiguredDiscoveryError(Exception):
    """Raised when a site has no way to discover URLs at all."""


class DiscoveryRunner:
    """Runs one discovery pass for a site and upserts results into the manifest."""

    def __init__(self, manifest_store: ManifestStore) -> None:
        """Initialize the runner with the manifest store it persists results to.

        Args:
            manifest_store: Store used to record discovered URLs.
        """
        self._manifest_store = manifest_store

    async def run(self, site_name: str, site_config: SiteConfig) -> DiscoveryRunSummary:
        """Discover URLs for ``site_name`` and record them in the manifest.

        Args:
            site_name: Name of the configured source site.
            site_config: Configuration for the site, including its discovery,
                scope, and politeness settings.

        Returns:
            A summary of counts and completeness for this run.
        """
        run_id = str(uuid.uuid4())
        summary = DiscoveryRunSummary(run_id=run_id, site_name=site_name)
        config = site_config.crawler_config
        base_url = str(site_config.base_url).rstrip("/")
        _require_discovery_source(site_name, config)
        is_sitemap_source = config.discovery.source == "sitemap"

        if is_sitemap_source and config.discovery.cache_ttl_hours > 0:
            cached_summary = self._try_cached_summary(site_name, config, base_url, summary)
            if cached_summary is not None:
                return cached_summary

        config_fingerprint = _config_fingerprint(config, base_url)
        if is_sitemap_source:
            # Recorded up front so an exception below (robots, sitemap fetch,
            # or persistence) leaves the site's last recorded run marked
            # incomplete, rather than leaving a stale prior "complete" run in
            # place that a later call could still serve from cache.
            self._manifest_store.record_discovery_run(
                site_name,
                datetime.now(UTC),
                complete=False,
                config_fingerprint=config_fingerprint,
            )

        # Shared across robots, sitemap, and gap-crawl requests to this host so a
        # Crawl-delay floor or Retry-After suspension applies uniformly.
        rate_limiter = HostRateLimiter(min_delay=config.min_delay, max_delay=config.max_delay)
        robots = await fetch_robots_rules(
            base_url,
            config.politeness.user_agent,
            rate_limiter=rate_limiter,
        )
        summary.robots_txt_url = robots.url
        if not robots.reachable and config.robots_policy == "require":
            summary.complete = False
            logger.warning("robots.txt unreachable for %s; marking run incomplete", site_name)
            if is_sitemap_source:
                self._manifest_store.record_discovery_run(
                    site_name,
                    datetime.now(UTC),
                    complete=False,
                    config_fingerprint=config_fingerprint,
                )
            return summary

        effective_delay = resolve_effective_delay(
            configured_min_delay=config.min_delay,
            configured_max_delay=config.max_delay,
            crawl_delay=robots.crawl_delay if config.politeness.respect_crawl_delay else None,
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
        if is_sitemap_source:
            self._manifest_store.record_discovery_run(
                site_name,
                datetime.now(UTC),
                complete=summary.complete,
                config_fingerprint=config_fingerprint,
            )
        return summary

    def _try_cached_summary(
        self,
        site_name: str,
        config: CrawlerConfig,
        base_url: str,
        summary: DiscoveryRunSummary,
    ) -> DiscoveryRunSummary | None:
        """Rebuild a summary from the manifest if the last run is still fresh.

        Args:
            site_name: Name of the configured source site.
            config: The site's crawler configuration.
            base_url: The site's configured base URL, normalized as in
                ``_config_fingerprint``.
            summary: The run summary to fill in on a cache hit.

        Returns:
            The filled-in summary on a cache hit, or ``None`` if discovery
            should re-fetch robots.txt and the sitemap as usual.
        """
        last_run = self._manifest_store.get_last_discovery_run(site_name)
        if last_run is None or not last_run.complete:
            return None
        if last_run.config_fingerprint != _config_fingerprint(config, base_url):
            return None
        age = datetime.now(UTC) - last_run.completed_at
        if age >= timedelta(hours=config.discovery.cache_ttl_hours):
            return None

        records = self._manifest_store.list_by_site(site_name)
        summary.discovered = len(records)
        for record in records:
            if record.scope_status == "eligible":
                summary.eligible += 1
            else:
                reason = record.scope_reason or "unknown"
                summary.excluded_by_reason[reason] = summary.excluded_by_reason.get(reason, 0) + 1
        summary.complete = True
        summary.cached = True
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
            summary.sitemap_urls = sitemap_urls
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
                summary.excluded_by_reason[reason] = summary.excluded_by_reason.get(reason, 0) + 1

            record = ManifestRecord(
                site_name=site_name,
                source_url=url,
                canonical_url=canonicalize_url(url),
                discovery_source={source_tag},
                sitemap_lastmod=lastmod_by_url.get(url),
                first_seen_at=now,
                last_seen_at=now,
                scope_status=(
                    "eligible" if decision.eligible else _SCOPE_REASON_STATUS.get(decision.reason or "", "excluded")
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
