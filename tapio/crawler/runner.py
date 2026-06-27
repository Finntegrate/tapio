"""Runner that wires configuration into the crawler."""

import asyncio
import logging

from tapio.config.config_models import SiteConfig
from tapio.crawler.crawler import BaseCrawler, CrawlResult


class CrawlerRunner:
    """Runs an async crawler process to crawl websites and save HTML content.

    This class provides a high-level interface to run a crawler using site configurations
    and collect the scraped results.
    """

    def __init__(self) -> None:
        """Initialize the crawler runner with logging configuration."""
        self.logger = logging.getLogger(__name__)
        self.setup_logging()

    def setup_logging(self) -> None:
        """Set up logging configuration for the crawler runner."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.StreamHandler()],
        )

    async def run_async(
        self,
        site_name: str,
        site_config: SiteConfig,
    ) -> list[CrawlResult]:
        """Run the crawler asynchronously and return crawled page data.

        Args:
            site_name: Name/identifier of the site being crawled.
            site_config: Site configuration containing all crawler settings.

        Returns:
            List of CrawlResult dictionaries containing page data.
        """
        self.logger.info(
            "Starting async crawl for site '%s' with URL: %s",
            site_name,
            site_config.base_url,
        )

        # Create and configure the crawler
        crawler = BaseCrawler(site_name, site_config)

        # Run the crawler
        results = await crawler.crawl()

        self.logger.info("Async crawling completed. Processed %d items.", len(results))
        return results

    def run(
        self,
        site_name: str,
        site_config: SiteConfig,
    ) -> list[CrawlResult]:
        """Run the crawler synchronously and return crawled page data.

        This is a convenience method that wraps the async version.

        Args:
            site_name: Name/identifier of the site being crawled.
            site_config: Site configuration containing all crawler settings.

        Returns:
            List of CrawlResult dictionaries containing page data.
        """
        return asyncio.run(self.run_async(site_name, site_config))
