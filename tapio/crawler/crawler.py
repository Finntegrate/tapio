"""Web crawler using Cloudflare Browser Rendering /crawl API."""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

from dotenv import load_dotenv

from tapio.config.config_models import SiteConfig
from tapio.config.settings import DEFAULT_CONTENT_DIR, DEFAULT_DIRS
from tapio.crawler.client import crawl_site

logger = logging.getLogger(__name__)


class UrlMappingData(TypedDict):
    """File-path -> original-URL mapping metadata."""

    url: str
    timestamp: str
    content_type: str


class CrawlResult(TypedDict):
    """Data returned for each crawled page."""

    url: str
    html: str
    markdown: str
    title: str
    depth: int
    crawl_timestamp: str
    content_type: str


class BaseCrawler:
    """Crawler wrapping the Cloudflare /crawl API.

    Replaces the previous async httpx + BeautifulSoup implementation.
    Same public interface: instantiate with (site_name, site_config), await crawl().
    """

    def __init__(self, site_name: str, site_config: SiteConfig) -> None:
        """Initialize crawler with site configuration and Cloudflare credentials.

        Args:
            site_name: Site identifier (e.g. "migri").
            site_config: SiteConfig with crawler_config settings.

        Raises:
            ValueError: If CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is missing.
        """
        load_dotenv()

        self.site_name = site_name
        self.site_config = site_config

        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        if not self.account_id or not self.api_token:
            msg = "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set in environment (.env)"
            raise ValueError(msg)

        self.base_url = str(site_config.base_url)

        crawler_cfg = site_config.crawler_config
        self.max_depth = crawler_cfg.max_depth
        self.limit = crawler_cfg.limit
        self.render = crawler_cfg.render
        self.source = crawler_cfg.source

        self.output_dir = str(Path(DEFAULT_CONTENT_DIR) / self.site_name / DEFAULT_DIRS["CRAWLED_DIR"])
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        self.url_mappings: dict[str, UrlMappingData] = {}
        self.mapping_file = str(Path(self.output_dir) / "url_mappings.json")

        if Path(self.mapping_file).exists():
            try:
                with Path(self.mapping_file).open(encoding="utf-8") as f:
                    self.url_mappings = json.load(f)
                logger.info("Loaded %d existing URL mappings", len(self.url_mappings))
            except Exception:
                logger.exception("Error loading URL mappings")

        logger.info("Cloudflare crawler ready for site '%s'", site_name)
        logger.info("Base URL: %s", self.base_url)
        logger.info("Depth: %s, Limit: %s, Render: %s, Source: %s", self.max_depth, self.limit, self.render, self.source)
        logger.info("Output directory: %s", self.output_dir)

    async def crawl(self) -> list[CrawlResult]:
        """Crawl the site via Cloudflare and return records.

        Returns:
            List of CrawlResult entries — one per page returned by Cloudflare.
        """
        logger.info("Starting Cloudflare crawl for %s", self.base_url)

        raw = crawl_site(
            account_id=self.account_id,
            api_token=self.api_token,
            url=self.base_url,
            depth=self.max_depth,
            limit=self.limit,
            render=self.render,
            source=self.source,
        )

        status = raw.get("status")
        records = raw.get("records", [])
        logger.info("Cloudflare status: %s, records returned: %d", status, len(records))

        results: list[CrawlResult] = []
        timestamp = datetime.now(UTC).isoformat()

        for record in records:
            if record.get("status") != "completed":
                logger.info("Skipping non-completed record: %s (%s)", record.get("url"), record.get("status"))
                continue

            url = record.get("url", "")
            markdown = record.get("markdown", "")
            metadata = record.get("metadata") or {}
            title = metadata.get("title", "")

            file_path = self._save_markdown_content(url, markdown)
            rel_path = os.path.relpath(file_path, self.output_dir)

            self.url_mappings[rel_path] = UrlMappingData(
                url=url,
                timestamp=timestamp,
                content_type="text/markdown",
            )

            results.append(
                CrawlResult(
                    url=url,
                    html="",
                    markdown=markdown,
                    title=title,
                    depth=0,
                    crawl_timestamp=timestamp,
                    content_type="text/markdown",
                ),
            )

        self._save_url_mappings()
        logger.info("Crawl finished. Saved %d pages.", len(results))
        return results
    
    def _save_markdown_content(self, url: str, markdown: str) -> str:
        """Write a page's markdown to disk under the site's crawled directory."""
        file_path = self._get_file_path_from_url(url)
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        with Path(file_path).open("w", encoding="utf-8") as f:
            f.write(markdown)

        logger.info("Saved markdown to %s", file_path)
        return file_path

    def _get_file_path_from_url(self, url: str) -> str:
        """Convert a URL to a filesystem path under output_dir, using a .md extension."""
        parsed_url = urlparse(url)
        path = parsed_url.path

        if not path or path == "/":
            path = "index.md"
        elif not path.endswith(".md"):
            path = path.rstrip("/") + ".md"

        if parsed_url.query:
            safe_query = parsed_url.query.replace("=", "_").replace("&", "_")
            if path.endswith(".md"):
                path = path[:-3] + "_" + safe_query + ".md"
            else:
                path = path + "_" + safe_query + ".md"

        domain = parsed_url.netloc
        full_path = Path(self.output_dir) / domain / path.lstrip("/")

        abs_full_path = full_path.resolve()
        abs_output_dir = Path(self.output_dir).resolve()
        if not abs_full_path.is_relative_to(abs_output_dir):
            msg = f"Invalid URL results in path outside output directory: {url}"
            raise ValueError(msg)

        return str(full_path)

    def _save_url_mappings(self) -> None:
        """Persist the URL mapping dictionary to url_mappings.json."""
        try:
            with Path(self.mapping_file).open("w", encoding="utf-8") as f:
                json.dump(self.url_mappings, f, indent=2, ensure_ascii=False)
            logger.debug("Saved %d URL mappings to %s", len(self.url_mappings), self.mapping_file)
        except Exception:
            logger.exception("Error saving URL mappings")

