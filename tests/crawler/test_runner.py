"""Tests for CrawlerRunner — the thin facade the CLI calls."""

import asyncio
from unittest.mock import MagicMock, patch

from pydantic import HttpUrl

from tapio.config.config_models import CrawlerConfig, SiteConfig
from tapio.crawler.runner import CrawlerRunner


def make_test_site_config() -> SiteConfig:
    """Build a minimal SiteConfig for runner tests."""
    return SiteConfig(
        base_url=HttpUrl("https://example.com"),
        crawler_config=CrawlerConfig(),
    )


class TestCrawlerRunner:
    """Behavior of the thin runner between CLI and BaseCrawler."""

    def test_run_calls_crawler_and_returns_results(self):
        fake_results = [
            {"url": "https://example.com/", "markdown": "# Home", "title": "Home"},
            {"url": "https://example.com/a", "markdown": "# A", "title": "A"},
        ]

        fake_crawler = MagicMock()
        fake_crawler.crawl.return_value = fake_results

        with patch("tapio.crawler.runner.BaseCrawler", return_value=fake_crawler) as mock_class:
            runner = CrawlerRunner()
            site_config = make_test_site_config()
            results = runner.run("site-x", site_config)

        mock_class.assert_called_once_with("site-x", site_config)
        fake_crawler.crawl.assert_called_once_with()
        assert results is fake_results

    def test_run_is_synchronous(self):
        assert asyncio.iscoroutinefunction(CrawlerRunner.run) is False
