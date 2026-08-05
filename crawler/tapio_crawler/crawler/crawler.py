"""Crawl4AI-backed renderer that turns due manifest records into Markdown.

Manifest-driven, per-URL rendering (Phase 2 of
docs/specs/crawler-improvements.md): ``discover`` populates the manifest,
this module consumes it. Unlike Phase 1's discovery (which reuses Crawl4AI's
``arun_many`` for a single-config batch), rendering calls ``arun()`` once per
URL under a bounded semaphore, because Requirement 5 needs a different
``CacheMode`` per record - something ``arun_many`` can't express with one
shared config for a whole batch.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import frontmatter

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.config.settings import (
    DEFAULT_CONTENT_DIR,
    DEFAULT_CRAWL4AI_BASE_DIRECTORY,
    DEFAULT_DIRS,
)
from tapio_crawler.crawler.policy import (
    EXTRACTOR_VERSION,
    MAX_RETRY_COUNT,
    RenderDecision,
    decide_render,
    retry_backoff_seconds,
)
from tapio_crawler.discovery.rate_limiter import HostRateLimiter, resolve_effective_delay
from tapio_crawler.discovery.robots import fetch_robots_rules
from tapio_crawler.discovery.scope import evaluate_scope
from tapio_crawler.manifest.models import ManifestRecord
from tapio_crawler.manifest.normalize import canonicalize_url
from tapio_crawler.manifest.store import ManifestStore

# Crawl4AI reads this when its database module is imported. This default keeps
# cache entries durable alongside the crawler's Markdown output, while allowing
# deployments to select a mounted volume explicitly.
os.environ.setdefault("CRAWL4_AI_BASE_DIRECTORY", DEFAULT_CRAWL4AI_BASE_DIRECTORY)

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.models import CrawlResult as Crawl4AIResult

logger = logging.getLogger(__name__)

EXCLUDED_TAGS = ["nav", "header", "footer", "form"]
TOO_MANY_REQUESTS_STATUS = 429
SERVICE_UNAVAILABLE_STATUS = 503


@dataclass
class RenderRunSummary:
    """Counts describing one render run, for the run's report/log line.

    Attributes:
        run_id: Unique identifier for this render run.
        site_name: Name of the configured source site.
        considered: Number of eligible manifest records evaluated for due-ness.
        skipped_not_due: Eligible records that were not due this run.
        rendered: Number of records for which a Crawl4AI ``arun()`` completed.
        saved: Number of records for which a Markdown document was written.
        low_quality: Renders whose cleaned Markdown was below the minimum
            content length and required a fallback retry.
        failed: Renders that failed outright (network error, non-2xx, or an
            unrecoverable low-quality result).
        retried: Renders that were scheduled for a future retry (failure or
            an unconfirmed cache-validation fallback).
        complete: Whether the run finished without a fatal interruption.
        eligible_total: Total eligible manifest records for this site, as of
            run completion.
        current_total: Eligible records with a successful current document,
            as of run completion.
    """

    run_id: str
    site_name: str
    considered: int = 0
    skipped_not_due: int = 0
    rendered: int = 0
    saved: int = 0
    low_quality: int = 0
    failed: int = 0
    retried: int = 0
    status_codes: dict[str, int] = field(default_factory=dict)
    cache_statuses: dict[str, int] = field(default_factory=dict)
    complete: bool = True
    eligible_total: int = 0
    current_total: int = 0

    @property
    def coverage_percent(self) -> float:
        """Return the share of eligible URLs with a successful current document."""
        if self.eligible_total == 0:
            return 100.0
        return 100.0 * self.current_total / self.eligible_total


class Crawl4AICrawler:
    """Render due manifest records for one site into Markdown documents."""

    def __init__(
        self,
        site_name: str,
        site_config: SiteConfig,
        manifest_store: ManifestStore,
    ) -> None:
        """Initialize a renderer for one configured site.

        Args:
            site_name: Identifier used for output paths and manifest lookups.
            site_config: Site-specific collection and extraction settings.
            manifest_store: Store holding this site's discovered URL inventory.
        """
        self.site_name = site_name
        self.site_config = site_config
        self.config = site_config.crawler_config
        self.manifest_store = manifest_store
        self.output_dir = Path(DEFAULT_CONTENT_DIR) / site_name / DEFAULT_DIRS["PARSED_DIR"]
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(
        self,
        *,
        max_urls: int,
        batch_size: int,
        force: bool = False,
    ) -> RenderRunSummary:
        """Render every due manifest record for this site, up to ``max_urls``.

        Args:
            max_urls: Hard cap on the number of records rendered this run.
            batch_size: Manifest page size used while selecting due records.
            force: Ignore each record's refresh schedule and render every
                eligible record.

        Returns:
            A summary of counts and completeness for this run.
        """
        summary = RenderRunSummary(run_id=str(uuid.uuid4()), site_name=self.site_name)

        base_url = str(self.site_config.base_url).rstrip("/")
        robots = await fetch_robots_rules(base_url, self.config.politeness.user_agent)
        if not robots.reachable and self.config.robots_policy == "require":
            summary.complete = False
            logger.warning(
                "robots.txt unreachable for %s; marking render run incomplete",
                self.site_name,
            )
            return summary

        rate_limiter = HostRateLimiter(min_delay=self.config.min_delay, max_delay=self.config.max_delay)
        effective_delay = resolve_effective_delay(
            configured_min_delay=self.config.min_delay,
            configured_max_delay=self.config.max_delay,
            crawl_delay=robots.crawl_delay if self.config.politeness.respect_crawl_delay else None,
        )
        rate_limiter.min_delay = effective_delay.min_delay
        rate_limiter.max_delay = effective_delay.max_delay

        due = self._select_due_records(max_urls=max_urls, batch_size=batch_size, force=force, summary=summary)
        if due:
            semaphore = asyncio.Semaphore(self.config.max_concurrent)
            try:
                async with AsyncWebCrawler(config=self._browser_config()) as crawler:
                    await asyncio.gather(
                        *(
                            self._render_bounded(crawler, record, decision, rate_limiter, semaphore, summary)
                            for record, decision in due
                        ),
                    )
            except Exception:
                logger.exception("Render run failed for %s", self.site_name)
                summary.complete = False

        self._finalize_coverage(summary)
        logger.info("Render summary for %s: %s", self.site_name, summary)
        return summary

    def _select_due_records(
        self,
        *,
        max_urls: int,
        batch_size: int,
        force: bool,
        summary: RenderRunSummary,
    ) -> list[tuple[ManifestRecord, RenderDecision]]:
        """Page through eligible manifest records and select the due ones.

        Stops once the site's eligible set is exhausted or ``max_urls`` due
        records have been collected, whichever comes first.
        """
        due: list[tuple[ManifestRecord, RenderDecision]] = []
        now = datetime.now(UTC)
        after = ""
        while len(due) < max_urls:
            page = self.manifest_store.list_eligible_page(
                self.site_name,
                after_canonical_url=after,
                limit=batch_size,
            )
            if not page:
                break
            for record in page:
                summary.considered += 1
                decision = decide_render(
                    record,
                    trust_lastmod=self.config.discovery.trust_lastmod,
                    unchanged_audit_days=self.config.refresh.unchanged_audit_days,
                    now=now,
                    force=force,
                )
                if decision is None:
                    summary.skipped_not_due += 1
                    continue
                due.append((record, decision))
                if len(due) >= max_urls:
                    break
            after = page[-1].canonical_url
            if len(page) < batch_size:
                break
        return due

    async def _render_bounded(
        self,
        crawler: AsyncWebCrawler,
        record: ManifestRecord,
        decision: RenderDecision,
        rate_limiter: HostRateLimiter,
        semaphore: asyncio.Semaphore,
        summary: RenderRunSummary,
    ) -> None:
        """Render one record under the run's concurrency limit."""
        async with semaphore:
            await self._render_one(crawler, record, decision, rate_limiter, summary)

    async def _render_one(
        self,
        crawler: AsyncWebCrawler,
        record: ManifestRecord,
        decision: RenderDecision,
        rate_limiter: HostRateLimiter,
        summary: RenderRunSummary,
    ) -> None:
        """Render one manifest record and persist its outcome immediately.

        Persisting here - rather than batching updates until the whole run
        finishes - is what makes a stopped run resumable: whatever records
        already completed are already saved to the manifest.
        """
        await rate_limiter.wait_for_turn()
        now = datetime.now(UTC)
        run_config = self._run_config(cache_mode=decision.cache_mode)
        try:
            results = await crawler.arun(record.source_url, config=run_config)
            raw_result = cast("Crawl4AIResult", next(iter(results)))
        except Exception:
            logger.exception("Render failed for %s", record.source_url)
            self._save_failure(record, now, summary)
            return

        self._record_status(raw_result, summary)
        summary.rendered += 1

        if not raw_result.success:
            self._handle_failure(record, raw_result, now, summary, rate_limiter)
            return

        cache_status = str(getattr(raw_result, "cache_status", None) or "miss")
        if cache_status == "hit_validated":
            self._handle_confirmed(record, now)
        elif cache_status == "hit_fallback":
            self._handle_unconfirmed(record, now, summary)
        else:
            await self._handle_fresh_fetch(crawler, record, raw_result, now, summary)

    async def _handle_fresh_fetch(
        self,
        crawler: AsyncWebCrawler,
        record: ManifestRecord,
        raw_result: Crawl4AIResult,
        now: datetime,
        summary: RenderRunSummary,
    ) -> None:
        """Handle a real fetch (``cache_status == "miss"``): save or retry."""
        markdown = self._markdown(raw_result)
        if len(markdown.strip()) < self.config.minimum_content_length:
            summary.low_quality += 1
            fallback_result = await self._fallback_result(crawler, record.source_url)
            markdown = self._markdown(fallback_result)
            if not fallback_result.success or len(markdown.strip()) < self.config.minimum_content_length:
                logger.warning("Skipping unrecoverable near-empty result for %s", record.source_url)
                summary.failed += 1
                self._save_failure(record, now, summary)
                return
            raw_result = fallback_result

        final_url = str((raw_result.metadata or {}).get("url") or raw_result.url)
        resolved_canonical = canonicalize_url(final_url)
        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        title = str((raw_result.metadata or {}).get("title") or "Untitled document")

        base_update = {
            "source_url": final_url,
            "canonical_url": resolved_canonical,
            "fetch_status": "success",
            "validation_status": "rendered",
            "last_attempt_at": now,
            "last_rendered_at": now,
            "extractor_version": EXTRACTOR_VERSION,
            "content_hash": content_hash,
            "content_length": len(markdown),
            "title": title,
            "language": self._language(),
            "retry_count": 0,
            "retry_after": None,
        }

        if resolved_canonical != record.canonical_url:
            decision = evaluate_scope(final_url, self.config.scope)
            if not decision.eligible:
                logger.warning(
                    "Redirect target %s for %s is out of scope; discarding",
                    final_url,
                    record.source_url,
                )
                summary.failed += 1
                self._save_failure(record, now, summary)
                return
            new_record = record.model_copy(update=base_update)
            self.manifest_store.rekey(self.site_name, record.canonical_url, new_record)
            old_path = self.output_dir / self._filename(record.canonical_url)
            old_path.unlink(missing_ok=True)
            self._write_document(new_record, markdown)
        else:
            updated = record.model_copy(update=base_update)
            self.manifest_store.save(updated)
            self._write_document(updated, markdown)

        summary.saved += 1

    def _handle_failure(
        self,
        record: ManifestRecord,
        raw_result: Crawl4AIResult,
        now: datetime,
        summary: RenderRunSummary,
        rate_limiter: HostRateLimiter,
    ) -> None:
        """Record a render failure and extend the host suspension on 429/503."""
        summary.failed += 1
        status_code = getattr(raw_result, "status_code", None)
        if status_code in (TOO_MANY_REQUESTS_STATUS, SERVICE_UNAVAILABLE_STATUS):
            headers = getattr(raw_result, "response_headers", None) or {}
            rate_limiter.suspend_for_retry_after(headers.get("Retry-After"))
        self._save_failure(record, now, summary)

    def _save_failure(self, record: ManifestRecord, now: datetime, summary: RenderRunSummary) -> None:
        """Persist a failed attempt with exponential backoff, capped at ``MAX_RETRY_COUNT``."""
        retry_count, retry_after = self._next_retry(record, now, summary)
        updated = record.model_copy(
            update={
                "fetch_status": "failed",
                "last_attempt_at": now,
                "retry_count": retry_count,
                "retry_after": retry_after,
            },
        )
        self.manifest_store.save(updated)

    @staticmethod
    def _next_retry(
        record: ManifestRecord,
        now: datetime,
        summary: RenderRunSummary,
    ) -> tuple[int, datetime | None]:
        """Return the next retry count/timestamp for a failed or unconfirmed attempt.

        Counts it in ``summary.retried`` only when a future retry is actually
        scheduled (the cap isn't exceeded).
        """
        retry_count = record.retry_count + 1
        if retry_count > MAX_RETRY_COUNT:
            return retry_count, None
        summary.retried += 1
        return retry_count, now + timedelta(seconds=retry_backoff_seconds(retry_count))

    def _handle_confirmed(self, record: ManifestRecord, now: datetime) -> None:
        """Persist an HTTP-confirmed-fresh cache hit, without a browser render."""
        updated = record.model_copy(
            update={
                "validation_status": "confirmed",
                "fetch_status": "success",
                "last_attempt_at": now,
                "retry_count": 0,
                "retry_after": None,
            },
        )
        self.manifest_store.save(updated)

    def _handle_unconfirmed(self, record: ManifestRecord, now: datetime, summary: RenderRunSummary) -> None:
        """Persist an unconfirmed cache-validation fallback and schedule a retry."""
        retry_count, retry_after = self._next_retry(record, now, summary)
        updated = record.model_copy(
            update={
                "validation_status": "unconfirmed",
                "last_attempt_at": now,
                "retry_count": retry_count,
                "retry_after": retry_after,
            },
        )
        self.manifest_store.save(updated)

    def _finalize_coverage(self, summary: RenderRunSummary) -> None:
        """Compute the run's coverage ratio from the manifest's current state."""
        summary.eligible_total = self.manifest_store.count_by_site(self.site_name, scope_status="eligible")
        summary.current_total = self.manifest_store.count_by_site(
            self.site_name,
            scope_status="eligible",
            fetch_status="success",
        )

    def _run_config(self, *, cache_mode: CacheMode, apply_content_cleanup: bool = True) -> CrawlerRunConfig:
        """Build the versioned Crawl4AI configuration from our stable schema."""
        markdown_generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(),
            options=self.config.markdown_config.model_dump(),
        )
        return CrawlerRunConfig(
            cache_mode=cache_mode,
            check_cache_freshness=cache_mode is CacheMode.ENABLED,
            page_timeout=self.config.page_timeout * 1_000,
            word_count_threshold=self.config.word_count_threshold,
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
                    self.config.target_elements or None if apply_content_cleanup else None,
                )
            ),
            markdown_generator=markdown_generator,
            remove_consent_popups=(self.config.remove_consent_popups if apply_content_cleanup else False),
            remove_overlay_elements=(self.config.remove_overlay_elements if apply_content_cleanup else False),
            verbose=False,
        )

    def _browser_config(self) -> BrowserConfig:
        """Configure Crawl4AI to launch the installed stable Google Chrome.

        Identifies the crawler with its configured ``User-Agent`` instead of
        Crawl4AI's default browser-spoofing string, per Design Principle 7.
        """
        return BrowserConfig(
            browser_type="chromium",
            chrome_channel="chrome",
            headless=True,
            user_agent=self.config.politeness.user_agent,
            verbose=False,
        )

    async def _fallback_result(self, crawler: AsyncWebCrawler, url: str) -> Crawl4AIResult:
        """Retry one page without DOM cleanup or brittle selector overrides."""
        fallback_results = await crawler.arun(
            url,
            config=self._run_config(
                apply_content_cleanup=False,
                # The current cache entry produced unusable Markdown. Re-fetch the
                # page once and replace that entry rather than retrying the same hit.
                cache_mode=CacheMode.WRITE_ONLY,
            ),
        )
        return next(iter(fallback_results))

    def _language(self) -> str | None:
        """Return the site's single configured language, or ``None`` if ambiguous.

        No real language detection exists in this codebase or in Crawl4AI's
        metadata; using the configured scope is an honest simplification, not
        a stub - real detection is out of scope (semantic classification is a
        later, separately evaluated phase per the spec's non-goals).
        """
        languages = self.config.scope.languages
        return languages[0] if len(languages) == 1 else None

    def _record_status(self, raw_result: Crawl4AIResult, summary: RenderRunSummary) -> None:
        """Record HTTP and cache statuses from one render."""
        status_code = getattr(raw_result, "status_code", None)
        if status_code is not None:
            status = str(status_code)
            summary.status_codes[status] = summary.status_codes.get(status, 0) + 1
        cache_status = getattr(raw_result, "cache_status", None)
        if cache_status:
            summary.cache_statuses[cache_status] = summary.cache_statuses.get(cache_status, 0) + 1

    def _write_document(self, record: ManifestRecord, markdown: str) -> Path:
        """Write a rendered page to its canonical-keyed Markdown output path.

        Args:
            record: The manifest record, already updated with this render's
                metadata.
            markdown: Non-empty Markdown content selected for persistence.

        Returns:
            The path the document was written to.
        """
        output_file = self.output_dir / self._filename(record.canonical_url)
        document = frontmatter.Post(
            markdown,
            title=record.title,
            source_url=record.source_url,
            canonical_url=record.canonical_url,
            content_hash=record.content_hash,
            language=record.language,
            extractor_version=record.extractor_version,
            crawl_timestamp=(record.last_rendered_at or datetime.now(UTC)).isoformat(),
        )
        output_file.write_text(frontmatter.dumps(document), encoding="utf-8")
        return output_file

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

    @staticmethod
    def _filename(canonical_url: str) -> str:
        """Create a deterministic, filesystem-safe Markdown filename from a canonical URL."""
        parsed = urlparse(canonical_url)
        path = parsed.path.strip("/") or "index"
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path).strip("-.") or "index"
        if parsed.query:
            query = re.sub(r"[^A-Za-z0-9._-]+", "-", parsed.query).strip("-.")
            stem = f"{stem}-{query}" if query else stem
        digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:12]
        max_stem_length = 255 - len(".md") - len(digest) - 1
        stem = stem[:max_stem_length].rstrip("-.") or "document"
        return f"{stem}-{digest}.md"
