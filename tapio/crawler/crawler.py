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
    """Crawler wrapping the Cloudflare /crawl API."""

    def __init__(self, site_name: str, site_config: SiteConfig) -> None:
        """Initialize the crawler for one site."""
        load_dotenv()
        self.site_name = site_name
        self.site_config = site_config
        self._load_credentials()
        self._load_crawl_settings()
        self._prepare_output_dir()
        self._load_existing_mappings()
        self._log_startup()

    def _load_credentials(self) -> None:
        """Read Cloudflare credentials from environment, raise if missing."""
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        if not account_id or not api_token:
            msg = "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set in environment (.env)"
            raise ValueError(msg)
        self.account_id: str = account_id
        self.api_token: str = api_token

    def _load_crawl_settings(self) -> None:
        """Copy crawl parameters from site_config into instance attributes."""
        self.base_url = str(self.site_config.base_url)
        cfg = self.site_config.crawler_config
        self.max_depth = cfg.max_depth
        self.limit = cfg.limit
        self.render = cfg.render
        self.source = cfg.source

    def _prepare_output_dir(self) -> None:
        """Create the site's output directory if it doesn't exist."""
        self.output_dir = str(Path(DEFAULT_CONTENT_DIR) / self.site_name / DEFAULT_DIRS["CRAWLED_DIR"])
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def _load_existing_mappings(self) -> None:
        """Load previous URL mappings from disk if a mapping file exists."""
        self.url_mappings: dict[str, UrlMappingData] = {}
        self.mapping_file = str(Path(self.output_dir) / "url_mappings.json")

        if not Path(self.mapping_file).exists():
            return

        try:
            with Path(self.mapping_file).open(encoding="utf-8") as f:
                self.url_mappings = json.load(f)
            logger.info("Loaded %d existing URL mappings", len(self.url_mappings))
        except Exception:
            logger.exception("Error loading URL mappings")

    def _log_startup(self) -> None:
        """Log crawler configuration at startup."""
        logger.info("Cloudflare crawler ready for site '%s'", self.site_name)
        logger.info("Base URL: %s", self.base_url)
        logger.info(
            "Depth: %s, Limit: %s, Render: %s, Source: %s",
            self.max_depth,
            self.limit,
            self.render,
            self.source,
        )
        logger.info("Output directory: %s", self.output_dir)

    def crawl(self) -> list[CrawlResult]:
        """Run a full crawl and return the successful records."""
        raw = self._fetch_from_cloudflare()
        records = self._filter_completed(raw.get("records", []))
        results: list[CrawlResult] = []
        try:
            results = [self._process_record(r) for r in records]
        finally:
            self._save_url_mappings()
        logger.info("Crawl finished. Saved %d pages. ", len(results))
        return results

    def _fetch_from_cloudflare(self) -> dict:
        """Call the Cloudflare /crawl API and return the raw response."""
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
        logger.info("Cloudflare status: %s, records returned: %d", raw.get("status"), len(raw.get("records", [])))
        return raw

    def _filter_completed(self, records: list[dict]) -> list[dict]:
        """Return only records whose status is 'completed'."""
        return [r for r in records if r.get("status") == "completed"]

    def _process_record(self, record: dict) -> CrawlResult:
        """Save one record's markdown to disk, update mappings, return a CrawlResult."""
        url = record.get("url", "")
        markdown = record.get("markdown", "")
        title = (record.get("metadata") or {}).get("title", "")
        timestamp = datetime.now(UTC).isoformat()

        file_path = self._save_markdown_content(url, markdown)
        rel_path = os.path.relpath(file_path, self.output_dir)
        self.url_mappings[rel_path] = UrlMappingData(
            url=url,
            timestamp=timestamp,
            content_type="text/markdown",
        )

        return CrawlResult(
            url=url,
            html="",
            markdown=markdown,
            title=title,
            depth=0,
            crawl_timestamp=timestamp,
            content_type="text/markdown",
        )

    def _save_markdown_content(self, url: str, markdown: str) -> str:
        """Write markdown to a file derived from the URL, return the file path."""
        file_path = self._get_file_path_from_url(url)
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(file_path).open("w", encoding="utf-8") as f:
            f.write(markdown)
        logger.info("Saved markdown to %s", file_path)
        return file_path

    def _get_file_path_from_url(self, url: str) -> str:
        """Turn a URL into a safe .md filesystem path under output_dir."""
        parsed = urlparse(url)
        filename = self._path_to_filename(parsed.path)
        filename = self._append_query_to_filename(filename, parsed.query)
        full_path = Path(self.output_dir) / parsed.netloc / filename.lstrip("/")
        self._assert_within_output_dir(full_path)
        return str(full_path)

    def _path_to_filename(self, path: str) -> str:
        """Convert a URL path into an .md filename (index.md for root)."""
        if not path or path == "/":
            return "index.md"
        if not path.endswith(".md"):
            return path.rstrip("/") + ".md"
        return path

    def _append_query_to_filename(self, filename: str, query: str) -> str:
        """Append a sanitized query string to the filename before the .md extension."""
        if not query:
            return filename
        safe = query.replace("=", "_").replace("&", "_")
        if filename.endswith(".md"):
            return filename[:-3] + "_" + safe + ".md"
        return filename + "_" + safe + ".md"

    def _assert_within_output_dir(self, path: Path) -> None:
        """Raise if the resolved path escapes the output directory."""
        abs_path = path.resolve()
        abs_out = Path(self.output_dir).resolve()
        if not abs_path.is_relative_to(abs_out):
            msg = f"Invalid URL results in path outside output directory: {path}"
            raise ValueError(msg)

    def _save_url_mappings(self) -> None:
        """Persist the URL mapping dictionary to url_mappings.json."""
        try:
            with Path(self.mapping_file).open("w", encoding="utf-8") as f:
                json.dump(self.url_mappings, f, indent=2, ensure_ascii=False)
            logger.debug("Saved %d URL mappings to %s", len(self.url_mappings), self.mapping_file)
        except Exception:
            logger.exception("Error saving URL mappings")
