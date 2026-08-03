"""Runner that wires a site configuration into the Crawl4AI crawler."""

import asyncio

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.crawler.crawler import Crawl4AICrawler, CrawlResult, CrawlSummary


class CrawlerRunner:
    """Run one configured Crawl4AI collection job."""

    def __init__(self) -> None:
        self.last_summary: CrawlSummary | None = None

    async def run_async(
        self,
        site_name: str,
        site_config: SiteConfig,
        *,
        force: bool = False,
    ) -> list[CrawlResult]:
        crawler = Crawl4AICrawler(site_name, site_config)
        results = await crawler.crawl(force=force)
        self.last_summary = crawler.summary
        return results

    def run(
        self,
        site_name: str,
        site_config: SiteConfig,
        *,
        force: bool = False,
    ) -> list[CrawlResult]:
        """Synchronous convenience wrapper for the Typer command."""
        return asyncio.run(self.run_async(site_name, site_config, force=force))
