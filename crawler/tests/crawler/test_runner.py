from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import HttpUrl

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.crawler.crawler import RenderRunSummary
from tapio_crawler.crawler.runner import CrawlerRunner


@pytest.mark.asyncio
async def test_runner_wires_site_config_to_crawl4ai_crawler() -> None:
    config = SiteConfig(base_url=HttpUrl("https://example.com"))
    manifest_store = MagicMock()
    summary = RenderRunSummary(run_id="abc", site_name="example")

    with patch("tapio_crawler.crawler.runner.Crawl4AICrawler") as crawler_type:
        crawler_type.return_value.crawl = AsyncMock(return_value=summary)

        runner = CrawlerRunner(manifest_store)
        result = await runner.run_async("example", config, max_urls=5_000, batch_size=500)

    crawler_type.assert_called_once_with("example", config, manifest_store)
    crawler_type.return_value.crawl.assert_awaited_once_with(max_urls=5_000, batch_size=500, force=False)
    assert result is summary


def test_runner_runs_crawler_synchronously() -> None:
    config = SiteConfig(base_url=HttpUrl("https://example.com"))
    manifest_store = MagicMock()
    summary = RenderRunSummary(run_id="abc", site_name="example")

    with patch("tapio_crawler.crawler.runner.Crawl4AICrawler") as crawler_type:
        crawler_type.return_value.crawl = AsyncMock(return_value=summary)

        result = CrawlerRunner(manifest_store).run("example", config, max_urls=5_000, batch_size=500)

    crawler_type.assert_called_once_with("example", config, manifest_store)
    assert result is summary
