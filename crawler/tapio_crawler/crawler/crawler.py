"""Crawl4AI-backed crawler that writes RAG-ready Markdown documents."""

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import NotRequired, TypedDict
from urllib.parse import urlparse

import frontmatter
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.config.settings import DEFAULT_CONTENT_DIR, DEFAULT_DIRS

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


class Crawl4AICrawler:
    """Collect one site with automatic content pruning and bounded traversal."""

    def __init__(self, site_name: str, site_config: SiteConfig) -> None:
        self.site_name = site_name
        self.site_config = site_config
        self.config = site_config.crawler_config
        self.output_dir = (
            Path(DEFAULT_CONTENT_DIR) / site_name / DEFAULT_DIRS["PARSED_DIR"]
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _run_config(self) -> CrawlerRunConfig:
        """Build the versioned Crawl4AI configuration from our stable schema."""
        markdown_generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(),
            options=self.config.markdown_config.model_dump(),
        )
        return CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=self.config.page_timeout * 1_000,
            excluded_tags=EXCLUDED_TAGS,
            css_selector=self.config.css_selector,
            target_elements=self.config.target_elements or None,
            markdown_generator=markdown_generator,
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=self.config.max_depth,
                max_pages=self.config.max_pages,
                include_external=False,
            ),
            # BFSDeepCrawlStrategy uses these when it calls arun_many for each level.
            mean_delay=self.config.min_delay,
            max_range=self.config.max_delay - self.config.min_delay,
            semaphore_count=self.config.max_concurrent,
            verbose=False,
        )

    async def crawl(self) -> list[CrawlResult]:
        """Run the Crawl4AI job and save each useful result as Markdown."""
        browser_config = BrowserConfig(headless=True, verbose=False)
        async with AsyncWebCrawler(config=browser_config) as crawler:
            raw_results = await crawler.arun(
                str(self.site_config.base_url),
                config=self._run_config(),
            )

        saved_results: list[CrawlResult] = []
        for raw_result in raw_results:
            if not raw_result.success:
                logger.warning(
                    "Skipping failed crawl for %s: %s",
                    raw_result.url,
                    raw_result.error_message,
                )
                continue

            markdown = self._markdown(raw_result)
            if len(markdown.strip()) < self.config.minimum_content_length:
                logger.warning(
                    "Skipping near-empty Crawl4AI result for %s (%d characters)",
                    raw_result.url,
                    len(markdown.strip()),
                )
                continue

            saved_results.append(self._save_result(raw_result, markdown))

        logger.info(
            "Saved %d Markdown documents for %s", len(saved_results), self.site_name
        )
        return saved_results

    @staticmethod
    def _markdown(raw_result: object) -> str:
        """Prefer the content-filtered Markdown that Crawl4AI exposes."""
        markdown = getattr(raw_result, "markdown", None)
        if markdown is None:
            return ""
        filtered = getattr(markdown, "fit_markdown", None)
        return str(filtered if filtered is not None else markdown)

    def _save_result(self, raw_result: object, markdown: str) -> CrawlResult:
        metadata = getattr(raw_result, "metadata", None) or {}
        source_url = str(metadata.get("url") or raw_result.url)  # type: ignore[attr-defined]
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
        return f"{stem}.md"
