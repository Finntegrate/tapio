from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapio_crawler.config.config_models import CrawlerConfig, SiteConfig
from tapio_crawler.crawler.runner import CrawlerRunner


def create_test_site_config(
    base_url: str = "https://example.com",
    description: str | None = None,
    depth: int = 1,
    delay_between_requests: float = 1.0,
    max_concurrent: int = 5,
) -> SiteConfig:
    """Create a test SiteConfig for testing purposes."""
    from pydantic import HttpUrl

    return SiteConfig(
        base_url=HttpUrl(base_url),
        description=description,
        crawler_config=CrawlerConfig(
            max_depth=depth,
            delay_between_requests=delay_between_requests,
            max_concurrent=max_concurrent,
        ),
    )


class TestCrawlerRunner:
    """Test the CrawlerRunner class that manages the crawling process."""

    def setup_method(self):
        self.runner = CrawlerRunner()

    @patch("tapio_crawler.crawler.runner.BaseCrawler")
    def test_run_basic(self, mock_base_crawler):
        """Test the basic functionality of the run method."""
        # Mock BaseCrawler instance
        mock_crawler_instance = MagicMock()
        mock_crawler_instance.crawl = AsyncMock(
            return_value=[
                {
                    "url": "https://example.com",
                    "html": "<html><body>Test</body></html>",
                    "depth": 0,
                    "crawl_timestamp": "2023-01-01T00:00:00",
                    "content_type": "text/html",
                },
            ],
        )
        mock_base_crawler.return_value = mock_crawler_instance

        # Create test configuration
        site_config = create_test_site_config()

        # Call the run method
        results = self.runner.run("test_site", site_config)

        # Verify BaseCrawler was instantiated with correct parameters
        mock_base_crawler.assert_called_once_with("test_site", site_config)

        # Verify crawler.crawl was called
        mock_crawler_instance.crawl.assert_called_once()

        # Verify results were returned
        assert len(results) == 1
        assert results[0]["url"] == "https://example.com"

    @patch("tapio_crawler.crawler.runner.BaseCrawler")
    def test_run_with_custom_config(self, mock_base_crawler):
        """Test the run method with custom configuration settings."""
        # Mock BaseCrawler instance
        mock_crawler_instance = MagicMock()
        mock_crawler_instance.crawl = AsyncMock(return_value=[])
        mock_base_crawler.return_value = mock_crawler_instance

        # Create test configuration with custom settings
        site_config = create_test_site_config(
            base_url="https://custom.example.com",
            description="Custom test site",
            depth=3,
            delay_between_requests=2.0,
            max_concurrent=10,
        )

        # Call the run method
        self.runner.run("custom_site", site_config)

        # Verify BaseCrawler was instantiated with the site config
        mock_base_crawler.assert_called_once_with("custom_site", site_config)

    @patch("tapio_crawler.crawler.runner.BaseCrawler")
    @pytest.mark.asyncio
    async def test_run_async(self, mock_base_crawler):
        """Test the async run_async method."""
        # Mock BaseCrawler instance
        mock_crawler_instance = MagicMock()
        mock_crawler_instance.crawl = AsyncMock(
            return_value=[
                {
                    "url": "https://example.com",
                    "html": "<html><body>Test</body></html>",
                    "depth": 0,
                    "crawl_timestamp": "2023-01-01T00:00:00",
                    "content_type": "text/html",
                },
            ],
        )
        mock_base_crawler.return_value = mock_crawler_instance

        # Create test configuration
        site_config = create_test_site_config(depth=2)

        # Call the async run method
        results = await self.runner.run_async("async_site", site_config)

        # Verify BaseCrawler was instantiated correctly
        mock_base_crawler.assert_called_once_with("async_site", site_config)

        # Verify crawler.crawl was called
        mock_crawler_instance.crawl.assert_called_once()

        # Verify results were returned
        assert len(results) == 1
        assert results[0]["url"] == "https://example.com"
