"""Tests for the discovery runner."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapio_crawler.config.config_models import (
    CrawlerConfig,
    DiscoveryConfig,
    GapCrawlConfig,
    ScopeConfig,
    SiteConfig,
)
from tapio_crawler.discovery.gap_crawl import GapCrawlResult
from tapio_crawler.discovery.robots import RobotsRules
from tapio_crawler.discovery.runner import DiscoveryRunner, MisconfiguredDiscoveryError
from tapio_crawler.discovery.sitemap import SitemapDiscoveryResult, SitemapUrlEntry
from tapio_crawler.manifest.store import ManifestStore


def _site_config(**crawler_overrides: object) -> SiteConfig:
    """Build a minimal ``SiteConfig``, overriding fields on its crawler config.

    Args:
        **crawler_overrides: Field values to override on the ``CrawlerConfig``.

    Returns:
        The constructed site configuration.
    """
    return SiteConfig(
        base_url="https://example.com",
        crawler_config=CrawlerConfig(**crawler_overrides),
    )


@pytest.fixture
def store(tmp_path: Path) -> Generator[ManifestStore]:
    """Yield a ``ManifestStore`` backed by a temporary database file."""
    manifest_store = ManifestStore(path=str(tmp_path / "manifest.db"))
    yield manifest_store
    manifest_store.close()


@pytest.mark.asyncio
async def test_raises_when_no_sitemap_and_no_gap_crawl(store: ManifestStore) -> None:
    """A site with no sitemap and no gap-crawl configured raises."""
    runner = DiscoveryRunner(store)
    site_config = _site_config(discovery=DiscoveryConfig(source="none"))

    with pytest.raises(MisconfiguredDiscoveryError):
        await runner.run("example", site_config)


@pytest.mark.asyncio
async def test_marks_run_incomplete_when_robots_unreachable(
    store: ManifestStore,
) -> None:
    """An unreachable robots.txt marks the run incomplete with no discoveries."""
    runner = DiscoveryRunner(store)
    site_config = _site_config(
        discovery=DiscoveryConfig(source="sitemap", sitemap_urls=["https://example.com/sitemap.xml"]),
    )

    with patch(
        "tapio_crawler.discovery.runner.fetch_robots_rules",
        AsyncMock(return_value=RobotsRules(reachable=False)),
    ):
        summary = await runner.run("example", site_config)

    assert summary.complete is False
    assert summary.discovered == 0


@pytest.mark.asyncio
async def test_sitemap_discovery_upserts_eligible_and_excluded_urls(
    store: ManifestStore,
) -> None:
    """Sitemap discovery upserts both eligible and excluded URLs, tagged with
    their scope status.
    """
    runner = DiscoveryRunner(store)
    site_config = _site_config(
        discovery=DiscoveryConfig(source="sitemap", sitemap_urls=["https://example.com/sitemap.xml"]),
        scope=ScopeConfig(allowed_domains=["example.com"], exclude_url_patterns=["*/search*"]),
    )

    fake_sitemap_result = SitemapDiscoveryResult(
        urls=[
            SitemapUrlEntry(url="https://example.com/a"),
            SitemapUrlEntry(url="https://example.com/search"),
        ],
        child_sitemaps_fetched=1,
        complete=True,
    )

    with (
        patch(
            "tapio_crawler.discovery.runner.fetch_robots_rules",
            AsyncMock(return_value=RobotsRules(reachable=True)),
        ),
        patch(
            "tapio_crawler.discovery.runner.discover_sitemap_urls",
            AsyncMock(return_value=fake_sitemap_result),
        ),
    ):
        summary = await runner.run("example", site_config)

    assert summary.discovered == 2
    assert summary.eligible == 1
    assert summary.excluded_by_reason == {"excluded_by_pattern": 1}

    records = store.list_by_site("example")
    assert len(records) == 2
    eligible = next(r for r in records if r.canonical_url.endswith("/a"))
    assert eligible.scope_status == "eligible"
    excluded = next(r for r in records if r.canonical_url.endswith("/search"))
    assert excluded.scope_status == "excluded"


@pytest.mark.asyncio
async def test_gap_crawl_discovery_used_when_no_sitemap(store: ManifestStore) -> None:
    """Gap-crawl discovery is used when no sitemap source is configured."""
    runner = DiscoveryRunner(store)
    site_config = _site_config(
        discovery=DiscoveryConfig(source="none"),
        gap_crawl=GapCrawlConfig(enabled=True, seed_urls=["https://example.com"]),
        scope=ScopeConfig(allowed_domains=["example.com"]),
    )

    with (
        patch(
            "tapio_crawler.discovery.runner.fetch_robots_rules",
            AsyncMock(return_value=RobotsRules(reachable=True)),
        ),
        patch(
            "tapio_crawler.discovery.runner.discover_via_gap_crawl",
            AsyncMock(
                return_value=GapCrawlResult(urls=["https://example.com/b"], complete=True),
            ),
        ),
    ):
        summary = await runner.run("example", site_config)

    assert summary.discovered == 1
    assert summary.eligible == 1
