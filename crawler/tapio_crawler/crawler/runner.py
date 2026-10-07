"""Runner that wires a site configuration into the manifest-driven renderer."""

import asyncio

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.crawler.crawler import Crawl4AICrawler, RenderRunSummary
from tapio_crawler.crawler.job_control import JobControl, SiteProgress
from tapio_crawler.manifest.store import ManifestStore


class CrawlerRunner:
    """Run one manifest-driven render job for a site."""

    def __init__(self, manifest_store: ManifestStore) -> None:
        """Initialize the runner with the manifest store it renders from.

        Args:
            manifest_store: Store holding discovered URL inventories.
        """
        self._manifest_store = manifest_store

    async def run_async(  # noqa: PLR0913
        self,
        site_name: str,
        site_config: SiteConfig,
        *,
        max_urls: int,
        batch_size: int,
        force: bool = False,
        retry: bool = False,
        include_inactive: bool = False,
        control: JobControl | None = None,
        progress: SiteProgress | None = None,
    ) -> RenderRunSummary:
        """Render one site's due manifest records asynchronously.

        Args:
            site_name: Identifier for the configured site.
            site_config: Collection settings for that site.
            max_urls: Hard cap on the number of records rendered this run.
            batch_size: Manifest page size used while selecting due records.
            force: Ignore each record's refresh schedule and render every
                eligible record.
            retry: Re-select failed records instead of following the refresh
                schedule.
            include_inactive: With ``retry``, also re-select
                ``inactive_candidate`` records.
            control: Optional pause/cancel control for the run.
            progress: Optional live progress object for the run.

        Returns:
            A summary of counts and completeness for this run.
        """
        crawler = Crawl4AICrawler(site_name, site_config, self._manifest_store)
        return await crawler.crawl(
            max_urls=max_urls,
            batch_size=batch_size,
            force=force,
            retry=retry,
            include_inactive=include_inactive,
            control=control,
            progress=progress,
        )

    def run(
        self,
        site_name: str,
        site_config: SiteConfig,
        *,
        max_urls: int,
        batch_size: int,
        force: bool = False,
    ) -> RenderRunSummary:
        """Synchronous convenience wrapper for the Typer command."""
        return asyncio.run(
            self.run_async(site_name, site_config, max_urls=max_urls, batch_size=batch_size, force=force),
        )
