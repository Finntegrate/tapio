"""Tests for the Crawl4AI-backed crawler."""

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


def test_run_config_uses_content_filtering_and_bounded_bfs() -> None:
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
    assert output.name == "permit-id-1.md"


@pytest.mark.asyncio
async def test_crawl_rejects_failed_and_near_empty_results(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler("example", site_config())
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(return_value=browser)
    browser.__aexit__ = AsyncMock(return_value=None)
    browser.arun = AsyncMock(
        return_value=[raw_result(success=False), raw_result(markdown="short")]
    )

    with patch("tapio_crawler.crawler.crawler.AsyncWebCrawler", return_value=browser):
        assert await crawler.crawl() == []

    assert crawler.summary["failed"] == 1
    assert crawler.summary["near_empty"] == 1
    assert crawler.summary["fallback_retries"] == 1
    assert crawler.summary["fallback_recoveries"] == 0


@pytest.mark.asyncio
async def test_crawl_retries_cleanup_induced_near_empty_result(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path)
    crawler = Crawl4AICrawler("example", site_config())
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(return_value=browser)
    browser.__aexit__ = AsyncMock(return_value=None)
    browser.arun = AsyncMock(side_effect=[[raw_result(markdown="short")], [raw_result()]])

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
