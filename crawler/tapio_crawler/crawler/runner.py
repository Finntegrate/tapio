"""Runner that wires a site configuration into the Crawl4AI crawler."""

import asyncio

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.crawler.crawler import Crawl4AICrawler, CrawlResult


class CrawlerRunner:
    """Run one configured Crawl4AI collection job."""

    async def run_async(
        self,
        site_name: str,
        site_config: SiteConfig,
    ) -> list[CrawlResult]:
        return await Crawl4AICrawler(site_name, site_config).crawl()

    def run(self, site_name: str, site_config: SiteConfig) -> list[CrawlResult]:
        """Synchronous convenience wrapper for the Typer command."""
        return asyncio.run(self.run_async(site_name, site_config))
