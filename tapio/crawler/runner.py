"""Runner that wires configuration into the crawler."""

import logging

from tapio.config.config_models import SiteConfig
from tapio.crawler.crawler import BaseCrawler, CrawlResult


class CrawlerRunner:
    """Thin facade the CLI calls to run a crawl for one site ."""

    def __init__(self) -> None:
        """Initialize the runner and set up logging."""
        self.logger = logging.getLogger(__name__)
        self.setup_logging()

    def setup_logging(self) -> None:
        """Configure logging format for the crawler runner."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.StreamHandler()],
        )

    def run(self, site_name: str, site_config: SiteConfig) -> list[CrawlResult]:
        """Build a crawler for this site , run it , return the results."""
        self.logger.info("Starting crawl for site '%s' with URL: %s", site_name, site_config.base_url)

        crawler = BaseCrawler(site_name, site_config)
        results = crawler.crawl()

        if not results:
            self.logger.warning(
                "Crawl returned 0 pages for '%s'. Check credentials , base_urls  and crawler_config.",
                site_name,
            )

        self.logger.info("Crawl completed. Processed %d items.", len(results))
        return results
