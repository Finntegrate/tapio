"""Tests for the Crawl4AI-backed crawler."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import frontmatter
import pytest
from pydantic import HttpUrl

from tapio_crawler.config.config_models import CrawlerConfig, SiteConfig
from tapio_crawler.crawler.crawler import Crawl4AICrawler


def site_config(**overrides) -> SiteConfig:
    return SiteConfig(
        base_url=HttpUrl("https://example.com"),
        crawler_config=CrawlerConfig(max_depth=0, max_pages=1, **overrides),
    )


def raw_result(
    *,
    success: bool = True,
    markdown: str = "Useful content " * 20,
    url: str = "https://example.com/permit?id=1",
) -> SimpleNamespace:
    return SimpleNamespace(
        success=success,
        markdown=SimpleNamespace(fit_markdown=markdown),
        metadata={"url": url, "title": "Residence permit", "depth": 0},
        url=url,
        status_code=200,
        error_message="failed" if not success else None,
    )


class CachedMarkdown:
    """Cached Crawl4AI Markdown whose filtered field was not persisted."""

    def __init__(self, content: str) -> None:
        self.fit_markdown = ""
        self.raw_markdown = content


def test_run_config_uses_content_filtering_and_bounded_bfs(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler(
        "example",
        site_config(
            min_delay=1,
            max_delay=2,
            remove_consent_popups=True,
            remove_overlay_elements=True,
        ),
    )
    config = crawler._run_config()

    assert config.excluded_tags == ["nav", "header", "footer", "form"]
    assert config.deep_crawl_strategy.max_pages == 1
    assert config.deep_crawl_strategy.include_external is False
    assert config.mean_delay == 1
    assert config.max_range == 1
    assert config.semaphore_count == 3
    assert config.cache_mode.name == "ENABLED"
    assert config.check_cache_freshness is True
    assert config.remove_consent_popups is True
    assert config.remove_overlay_elements is True


def test_fallback_config_disables_brittle_cleanup() -> None:
    crawler = Crawl4AICrawler(
        "example",
        site_config(
            css_selector="#content-root",
            remove_consent_popups=True,
            remove_overlay_elements=True,
        ),
    )

    config = crawler._run_config(deep_crawl=False, apply_content_cleanup=False)

    assert config.deep_crawl_strategy is None
    assert config.css_selector is None
    assert config.target_elements == []
    assert config.remove_consent_popups is False
    assert config.remove_overlay_elements is False


def test_crawl_uses_the_installed_chrome_channel() -> None:
    crawler = Crawl4AICrawler("example", site_config())
    browser_config = crawler._browser_config()

    assert browser_config.browser_type == "chromium"
    assert browser_config.chrome_channel == "chrome"


def test_markdown_uses_cached_raw_markdown_when_filtered_value_is_empty() -> None:
    raw_result_with_cached_markdown = SimpleNamespace(
        markdown=CachedMarkdown("Cached document content"),
    )

    assert Crawl4AICrawler._markdown(raw_result_with_cached_markdown) == ("Cached document content")


@pytest.mark.asyncio
async def test_crawl_writes_frontmatter_markdown(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler("example", site_config())
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(return_value=browser)
    browser.__aexit__ = AsyncMock(return_value=None)
    browser.arun = AsyncMock(return_value=[raw_result()])

    with patch("tapio_crawler.crawler.crawler.AsyncWebCrawler", return_value=browser):
        results = await crawler.crawl()

    assert len(results) == 1
    output = Path(results[0]["output_file"])
    document = frontmatter.load(output)
    assert document.metadata["source_url"] == "https://example.com/permit?id=1"
    assert document.metadata["title"] == "Residence permit"
    assert "Useful content" in document.content
    digest = hashlib.sha256(b"https://example.com/permit?id=1").hexdigest()[:12]
    assert output.name == f"permit-id-1-{digest}.md"
    assert Crawl4AICrawler._filename("https://example.com/permit#one") != (
        Crawl4AICrawler._filename("https://example.com/permit#two")
    )
    state = json.loads((tmp_path / "example" / "crawl_state.json").read_text())
    assert state["recrawl_interval_hours"] == 720


@pytest.mark.asyncio
async def test_crawl_skips_site_within_recrawl_interval(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler("example", site_config(recrawl_interval_hours=720))
    crawler.state_path.write_text(
        json.dumps(
            {
                "last_successful_crawl_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            },
        ),
        encoding="utf-8",
    )

    with patch("tapio_crawler.crawler.crawler.AsyncWebCrawler") as crawler_type:
        assert await crawler.crawl() == []

    crawler_type.assert_not_called()
    assert crawler.summary["skipped"] is True


@pytest.mark.asyncio
async def test_force_crawl_ignores_recrawl_interval(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler("example", site_config())
    crawler.state_path.write_text(
        json.dumps({"last_successful_crawl_at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(return_value=browser)
    browser.__aexit__ = AsyncMock(return_value=None)
    browser.arun = AsyncMock(return_value=[raw_result()])

    with patch("tapio_crawler.crawler.crawler.AsyncWebCrawler", return_value=browser):
        results = await crawler.crawl(force=True)

    assert len(results) == 1
    assert crawler.summary["skipped"] is False


@pytest.mark.asyncio
async def test_crawl_rejects_failed_and_near_empty_results(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler("example", site_config())
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(return_value=browser)
    browser.__aexit__ = AsyncMock(return_value=None)
    browser.arun = AsyncMock(
        return_value=[raw_result(success=False), raw_result(markdown="short")],
    )

    with patch("tapio_crawler.crawler.crawler.AsyncWebCrawler", return_value=browser):
        assert await crawler.crawl() == []

    assert crawler.summary["failed"] == 1
    assert crawler.summary["near_empty"] == 1
    assert crawler.summary["fallback_retries"] == 1
    assert crawler.summary["fallback_recoveries"] == 0


@pytest.mark.asyncio
async def test_crawl_retries_cleanup_induced_near_empty_result(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler("example", site_config())
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(return_value=browser)
    browser.__aexit__ = AsyncMock(return_value=None)
    browser.arun = AsyncMock(
        side_effect=[[raw_result(markdown="short")], [raw_result()]],
    )

    with patch("tapio_crawler.crawler.crawler.AsyncWebCrawler", return_value=browser):
        results = await crawler.crawl()

    assert len(results) == 1
    assert crawler.summary["near_empty"] == 1
    assert crawler.summary["fallback_retries"] == 1
    assert crawler.summary["fallback_recoveries"] == 1
    assert crawler.summary["status_codes"] == {"200": 1}
    fallback_config = browser.arun.await_args_list[1].kwargs["config"]
    assert fallback_config.deep_crawl_strategy is None
    assert fallback_config.remove_consent_popups is False
    assert fallback_config.cache_mode.name == "WRITE_ONLY"


@pytest.mark.asyncio
async def test_crawl_handles_browser_launch_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler("example", site_config())
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(side_effect=RuntimeError("browser unavailable"))

    with patch("tapio_crawler.crawler.crawler.AsyncWebCrawler", return_value=browser):
        assert await crawler.crawl() == []

    assert crawler.summary["fetched"] == 0
