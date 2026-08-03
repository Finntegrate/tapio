"""Crawl4AI-backed crawler that writes RAG-ready Markdown documents."""

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from urllib.parse import urlparse

import frontmatter

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.config.settings import (
    DEFAULT_CONTENT_DIR,
    DEFAULT_CRAWL4AI_BASE_DIRECTORY,
    DEFAULT_DIRS,
)

# Crawl4AI reads this when its database module is imported. This default keeps
# cache entries durable alongside the crawler's Markdown output, while allowing
# deployments to select a mounted volume explicitly.
os.environ.setdefault("CRAWL4_AI_BASE_DIRECTORY", DEFAULT_CRAWL4AI_BASE_DIRECTORY)

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.models import CrawlResult as Crawl4AIResult
from crawl4ai.models import CrawlResultContainer

logger = logging.getLogger(__name__)

EXCLUDED_TAGS = ["nav", "header", "footer", "form"]


class CrawlResult(TypedDict):
    """A successfully saved Markdown document."""

    source_url: str
    output_file: str
    title: str
    markdown_length: int
    depth: int
    crawl_timestamp: str
    status_code: NotRequired[int | None]


class CrawlSummary(TypedDict):
    """Counters describing a completed crawl, including discarded results."""

    fetched: int
    saved: int
    failed: int
    near_empty: int
    fallback_retries: int
    fallback_recoveries: int
    status_codes: dict[str, int]
    cache_statuses: dict[str, int]
    skipped: bool


class Crawl4AICrawler:
    """Collect one site with automatic content pruning and bounded traversal."""

    def __init__(self, site_name: str, site_config: SiteConfig) -> None:
        """Initialize a crawler for one configured site.

        Args:
            site_name: Identifier used for output and crawl state paths.
            site_config: Site-specific collection and extraction settings.
        """
        self.site_name = site_name
        self.site_config = site_config
        self.config = site_config.crawler_config
        self.output_dir = (
            Path(DEFAULT_CONTENT_DIR) / site_name / DEFAULT_DIRS["PARSED_DIR"]
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output_dir.parent / "crawl_state.json"
        self.summary: CrawlSummary = self._empty_summary()

    def _run_config(
        self,
        *,
        deep_crawl: bool = True,
        apply_content_cleanup: bool = True,
        cache_mode: CacheMode = CacheMode.ENABLED,
    ) -> CrawlerRunConfig:
        """Build the versioned Crawl4AI configuration from our stable schema."""
        markdown_generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(),
            options=self.config.markdown_config.model_dump(),
        )
        return CrawlerRunConfig(
            cache_mode=cache_mode,
            check_cache_freshness=cache_mode is CacheMode.ENABLED,
            page_timeout=self.config.page_timeout * 1_000,
            excluded_tags=EXCLUDED_TAGS,
            # Crawl4AI accepts ``None`` for both options despite declaring the
            # parameters as non-optional. Preserve its documented defaults.
            css_selector=cast(
                "str",
                self.config.css_selector if apply_content_cleanup else None,
            ),
            target_elements=(
                cast(
                    "list[str]",
                    self.config.target_elements or None
                    if apply_content_cleanup
                    else None,
                )
            ),
            markdown_generator=markdown_generator,
            deep_crawl_strategy=(
                BFSDeepCrawlStrategy(
                    max_depth=self.config.max_depth,
                    max_pages=self.config.max_pages,
                    include_external=False,
                )
                if deep_crawl
                else None
            ),
            remove_consent_popups=(
                self.config.remove_consent_popups if apply_content_cleanup else False
            ),
            remove_overlay_elements=(
                self.config.remove_overlay_elements if apply_content_cleanup else False
            ),
            # BFSDeepCrawlStrategy uses these when it calls arun_many for each level.
            mean_delay=self.config.min_delay,
            max_range=self.config.max_delay - self.config.min_delay,
            semaphore_count=self.config.max_concurrent,
            verbose=False,
        )

    @staticmethod
    def _browser_config() -> BrowserConfig:
        """Configure Crawl4AI to launch the installed stable Google Chrome."""
        return BrowserConfig(
            browser_type="chromium",
            chrome_channel="chrome",
            headless=True,
            verbose=False,
        )

    async def crawl(self, *, force: bool = False) -> list[CrawlResult]:
        """Run the Crawl4AI job and save each useful result as Markdown."""
        self.summary = self._empty_summary()
        if not force and not self._is_due():
            self.summary["skipped"] = True
            logger.info(
                "Skipping %s; its %s-hour re-crawl interval has not elapsed",
                self.site_name,
                self.config.recrawl_interval_hours,
            )
            return []

        browser_config = self._browser_config()
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                raw_results = cast(
                    "CrawlResultContainer[Crawl4AIResult]",
                    await crawler.arun(
                        str(self.site_config.base_url),
                        config=self._run_config(),
                    ),
                )
                self.summary["fetched"] = len(raw_results)
                saved_results = await self._save_usable_results(crawler, raw_results)
        except Exception:
            logger.exception("Crawl failed for site %s", self.site_name)
            return []

        self.summary["saved"] = len(saved_results)
        if saved_results:
            self._write_crawl_state()
        logger.info(
            "Crawl summary for %s: %s",
            self.site_name,
            self.summary,
        )
        return saved_results

    async def _save_usable_results(
        self,
        crawler: AsyncWebCrawler,
        raw_results: CrawlResultContainer[Crawl4AIResult],
    ) -> list[CrawlResult]:
        """Persist useful results and retry cleanup-induced near-empty results once."""
        saved_results: list[CrawlResult] = []
        for raw_result in raw_results:
            self._record_status(raw_result)
            if not raw_result.success:
                self.summary["failed"] += 1
                logger.warning(
                    "Skipping failed crawl for %s: %s",
                    raw_result.url,
                    raw_result.error_message,
                )
                continue

            markdown = self._markdown(raw_result)
            if len(markdown.strip()) < self.config.minimum_content_length:
                self.summary["near_empty"] += 1
                self.summary["fallback_retries"] += 1
                logger.warning(
                    "Retrying near-empty Crawl4AI result for %s without cleanup",
                    raw_result.url,
                )
                raw_result = await self._fallback_result(crawler, raw_result.url)
                markdown = self._markdown(raw_result)
                if not raw_result.success or (
                    len(markdown.strip()) < self.config.minimum_content_length
                ):
                    logger.warning(
                        "Skipping unrecoverable near-empty result for %s",
                        raw_result.url,
                    )
                    continue
                self.summary["fallback_recoveries"] += 1

            saved_results.append(self._save_result(raw_result, markdown))
        return saved_results

    async def _fallback_result(
        self,
        crawler: AsyncWebCrawler,
        url: str,
    ) -> Crawl4AIResult:
        """Retry one page without DOM cleanup or brittle selector overrides."""
        fallback_results = await crawler.arun(
            url,
            config=self._run_config(
                deep_crawl=False,
                apply_content_cleanup=False,
                # The current cache entry produced unusable Markdown. Re-fetch the
                # page once and replace that entry rather than retrying the same hit.
                cache_mode=CacheMode.WRITE_ONLY,
            ),
        )
        return next(iter(fallback_results))

    def _record_status(self, raw_result: Crawl4AIResult) -> None:
        """Record HTTP and cache statuses from the primary bounded crawl."""
        status_code = getattr(raw_result, "status_code", None)
        if status_code is not None:
            status = str(status_code)
            self.summary["status_codes"][status] = (
                self.summary["status_codes"].get(status, 0) + 1
            )
        cache_status = getattr(raw_result, "cache_status", None)
        if cache_status:
            self.summary["cache_statuses"][cache_status] = (
                self.summary["cache_statuses"].get(cache_status, 0) + 1
            )

    def _is_due(self) -> bool:
        """Return whether this site has passed its successful-crawl interval."""
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            last_crawl = datetime.fromisoformat(state["last_successful_crawl_at"])
        except (
            FileNotFoundError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return True

        if last_crawl.tzinfo is None:
            last_crawl = last_crawl.replace(tzinfo=UTC)
        return datetime.now(UTC) >= last_crawl + timedelta(
            hours=self.config.recrawl_interval_hours,
        )

    def _write_crawl_state(self) -> None:
        """Atomically record a successful crawl for site-level scheduling."""
        state = {
            "last_successful_crawl_at": datetime.now(UTC).isoformat(),
            "recrawl_interval_hours": self.config.recrawl_interval_hours,
        }
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(self.state_path)

    @staticmethod
    def _empty_summary() -> CrawlSummary:
        return {
            "fetched": 0,
            "saved": 0,
            "failed": 0,
            "near_empty": 0,
            "fallback_retries": 0,
            "fallback_recoveries": 0,
            "status_codes": {},
            "cache_statuses": {},
            "skipped": False,
        }

    @staticmethod
    def _markdown(raw_result: Crawl4AIResult) -> str:
        """Prefer the content-filtered Markdown that Crawl4AI exposes."""
        markdown = raw_result.markdown
        if markdown is None:
            return ""
        filtered = markdown.fit_markdown
        # Crawl4AI caches raw Markdown and may restore ``fit_markdown`` as an
        # empty string. Prefer the filtered form only when it contains content.
        if filtered and filtered.strip():
            return str(filtered)
        raw_markdown = markdown.raw_markdown
        if raw_markdown and raw_markdown.strip():
            return str(raw_markdown)
        return ""

    def _save_result(self, raw_result: Crawl4AIResult, markdown: str) -> CrawlResult:
        """Write a crawled page to its deterministic Markdown output path.

        Args:
            raw_result: Crawl4AI result supplying source metadata.
            markdown: Non-empty Markdown content selected for persistence.

        Returns:
            Metadata describing the saved Markdown document.
        """
        metadata = raw_result.metadata or {}
        source_url = str(metadata.get("url") or raw_result.url)
        title = str(metadata.get("title") or "Untitled document")
        crawl_timestamp = datetime.now(UTC).isoformat()
        output_file = self.output_dir / self._filename(source_url)
        document = frontmatter.Post(
            markdown,
            title=title,
            source_url=source_url,
            crawl_timestamp=crawl_timestamp,
        )
        output_file.write_text(frontmatter.dumps(document), encoding="utf-8")
        return CrawlResult(
            source_url=source_url,
            output_file=str(output_file),
            title=title,
            markdown_length=len(markdown),
            depth=int(metadata.get("depth", 0)),
            crawl_timestamp=crawl_timestamp,
            status_code=getattr(raw_result, "status_code", None),
        )

    @staticmethod
    def _filename(source_url: str) -> str:
        """Create a deterministic, filesystem-safe Markdown filename from a URL."""
        parsed = urlparse(source_url)
        path = parsed.path.strip("/") or "index"
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path).strip("-.") or "index"
        if parsed.query:
            query = re.sub(r"[^A-Za-z0-9._-]+", "-", parsed.query).strip("-.")
            stem = f"{stem}-{query}" if query else stem
        digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:12]
        max_stem_length = 255 - len(".md") - len(digest) - 1
        stem = stem[:max_stem_length].rstrip("-.") or "document"
        return f"{stem}-{digest}.md"
