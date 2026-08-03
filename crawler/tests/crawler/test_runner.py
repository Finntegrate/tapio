from unittest.mock import AsyncMock, patch

import pytest
from pydantic import HttpUrl

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.crawler.runner import CrawlerRunner


@pytest.mark.asyncio
async def test_runner_wires_site_config_to_crawl4ai_crawler() -> None:
    config = SiteConfig(base_url=HttpUrl("https://example.com"))
    with patch("tapio_crawler.crawler.runner.Crawl4AICrawler") as crawler_type:
        crawler_type.return_value.crawl = AsyncMock(
            return_value=[{"source_url": "https://example.com"}]
        )

        runner = CrawlerRunner()
        results = await runner.run_async("example", config)

    crawler_type.assert_called_once_with("example", config)
    assert results == [{"source_url": "https://example.com"}]
    assert runner.last_summary is crawler_type.return_value.summary
