"""Bounded deep-crawl discovery: the only discovery path when no sitemap exists.

Discovery-only for Phase 1 - it records discovered, in-scope URLs but does
not persist rendered Markdown (that is Requirement 3/Phase 2's job).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Final

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import (
    ContentTypeFilter,
    DomainFilter,
    FilterChain,
    URLFilter,
)
from crawl4ai.models import CrawlResult

from tapio_crawler.config.config_models import GapCrawlConfig, ScopeConfig
from tapio_crawler.crawler.job_control import DiscoveryProgress, JobControl
from tapio_crawler.discovery.rate_limiter import HostRateLimiter, OperatorCancelledError

logger = logging.getLogger(__name__)


@dataclass
class GapCrawlResult:
    """Discovered URLs from one bounded deep-crawl discovery pass.

    Attributes:
        urls: Every URL found, including those from a resumed checkpoint.
        complete: Whether every page crawled successfully and the crawl ran to the end.
        cancelled: Whether an operator cancelled the crawl part-way.
        finished: Whether the crawl ran to the end, so its checkpoint is no longer needed.
            False after a cancel or an unexpected error, when the checkpoint is kept.
    """

    urls: list[str] = field(default_factory=list)
    complete: bool = True
    cancelled: bool = False
    finished: bool = True


CheckpointSaver = Callable[[dict[str, Any]], None]

# Crawl4AI reports its state after every page; saving it that often would mean a database
# write per page, so it's saved every few pages, and always when the crawl is cancelled.
_SAVE_EVERY_N_PAGES: Final = 10


async def discover_via_gap_crawl(  # noqa: PLR0913
    gap_crawl: GapCrawlConfig,
    scope: ScopeConfig,
    *,
    user_agent: str,
    rate_limiter: HostRateLimiter,
    max_concurrent: int,
    control: JobControl | None = None,
    checkpoint: dict[str, Any] | None = None,
    save_checkpoint: CheckpointSaver | None = None,
    progress: DiscoveryProgress | None = None,
) -> GapCrawlResult:
    """Run a bounded BFS crawl to discover URLs when no sitemap exists.

    Reuses ``rate_limiter``'s current delay window - shared with any robots
    or sitemap fetches already made for this host - rather than resetting
    host spacing with its own values.

    Each seed is crawled in turn with Crawl4AI's resumable BFS strategy (#178). Its crawl
    state, plus the URLs found so far, is handed to ``save_checkpoint`` as the crawl goes,
    and a later call given that ``checkpoint`` continues where it stopped instead of
    starting over. A pause holds the crawl between pages; a cancel stops it, saves the
    checkpoint, and returns a cancelled result.

    Args:
        gap_crawl: Seeds and bounds for the crawl.
        scope: Domains and content types the crawl may follow.
        user_agent: User agent to crawl as.
        rate_limiter: Host delay window to reuse.
        max_concurrent: Pages to fetch at once.
        control: Optional pause/cancel control.
        checkpoint: A checkpoint saved by an earlier, unfinished call, to resume from.
        save_checkpoint: Called with the checkpoint to persist as the crawl goes.
        progress: Updated with pages visited and queued, for the progress line.

    Returns:
        The URLs found, and whether the crawl finished, completed cleanly, or was cancelled.
    """
    if not gap_crawl.enabled or not gap_crawl.seed_urls:
        return GapCrawlResult(complete=False)

    crawl = _Checkpoint.load(checkpoint, save_checkpoint)
    if progress is not None:
        progress.resumed = checkpoint is not None

    browser_config = BrowserConfig(
        browser_type="chromium",
        chrome_channel="chrome",
        headless=True,
        user_agent=user_agent,
        verbose=False,
    )

    complete = True
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            await rate_limiter.wait_for_turn()
            for seed in gap_crawl.seed_urls:
                if seed in crawl.finished_seeds:
                    continue
                run_config = CrawlerRunConfig(
                    deep_crawl_strategy=_strategy(
                        gap_crawl, scope, seed=seed, crawl=crawl, control=control, progress=progress
                    ),
                    stream=True,
                    cache_mode=CacheMode.BYPASS,
                    mean_delay=rate_limiter.min_delay,
                    max_range=max(0.0, rate_limiter.max_delay - rate_limiter.min_delay),
                    semaphore_count=max_concurrent,
                    verbose=False,
                )
                complete = await crawl.collect(await crawler.arun(seed, config=run_config)) and complete
                if control is not None and control.cancelled:
                    crawl.save()
                    return GapCrawlResult(urls=crawl.discovered, complete=False, cancelled=True, finished=False)
                crawl.finish(seed)
    except OperatorCancelledError:
        crawl.save()
        raise
    except Exception:
        logger.exception("Gap-crawl discovery failed for %s", gap_crawl.seed_urls)
        crawl.save()
        return GapCrawlResult(urls=crawl.discovered, complete=False, finished=False)

    return GapCrawlResult(urls=crawl.discovered, complete=complete)


@dataclass
class _Checkpoint:
    """What a resumable gap crawl saves: Crawl4AI's state per seed, and the URLs found so far.

    Crawl4AI's state records which pages were visited but not which succeeded, so the
    discovered URLs are kept alongside it; otherwise pages found before a cancel would be
    skipped as visited on resume and never recorded.
    """

    saver: CheckpointSaver | None
    seed_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    finished_seeds: list[str] = field(default_factory=list)
    discovered: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, saved: dict[str, Any] | None, saver: CheckpointSaver | None) -> _Checkpoint:
        saved = saved or {}
        return cls(
            saver=saver,
            seed_states=dict(saved.get("seeds", {})),
            finished_seeds=list(saved.get("finished_seeds", [])),
            discovered=list(saved.get("discovered", [])),
        )

    def save(self) -> None:
        if self.saver is not None:
            self.saver(
                {"seeds": self.seed_states, "finished_seeds": self.finished_seeds, "discovered": self.discovered}
            )

    async def collect(self, raw: Any) -> bool:
        """Record each successful result's URL once; return whether every page succeeded."""
        all_succeeded = True
        seen = set(self.discovered)
        async for result in _results(raw):
            if not result.success:
                all_succeeded = False
            elif result.url not in seen:
                seen.add(result.url)
                self.discovered.append(result.url)
        return all_succeeded

    def finish(self, seed: str) -> None:
        self.finished_seeds.append(seed)
        self.seed_states.pop(seed, None)


def _strategy(
    gap_crawl: GapCrawlConfig,
    scope: ScopeConfig,
    *,
    seed: str,
    crawl: _Checkpoint,
    control: JobControl | None,
    progress: DiscoveryProgress | None,
) -> BFSDeepCrawlStrategy:
    """Build one seed's BFS strategy, wired to resume, report, pause, and cancel."""
    pages = 0

    async def on_state_change(state: dict[str, Any]) -> None:
        nonlocal pages
        crawl.seed_states[seed] = state
        pages += 1
        if progress is not None:
            progress.visited = len(state.get("visited", ()))
            progress.queued = len(state.get("pending", ()))
        cancelled = control is not None and control.cancelled
        if cancelled or pages % _SAVE_EVERY_N_PAGES == 0:
            crawl.save()
        if control is not None:
            # Crawl4AI awaits this between pages, so waiting out a pause here holds the crawl.
            await control.checkpoint()

    return BFSDeepCrawlStrategy(
        max_depth=gap_crawl.max_depth,
        max_pages=gap_crawl.max_pages,
        include_external=False,
        filter_chain=FilterChain(_build_filters(scope)),
        resume_state=crawl.seed_states.get(seed),
        on_state_change=on_state_change,
        should_cancel=(lambda: control.cancelled) if control is not None else None,
    )


async def _results(raw: Any) -> AsyncIterator[CrawlResult]:
    """Yield crawl results whether Crawl4AI returned a stream, a list, or a single result."""
    if hasattr(raw, "__aiter__"):
        async for result in raw:
            yield result
    elif isinstance(raw, list | tuple):
        for result in raw:
            yield result
    else:
        yield raw


def _build_filters(scope: ScopeConfig) -> list[URLFilter]:
    filters: list[URLFilter] = []
    if scope.allowed_domains:
        filters.append(DomainFilter(allowed_domains=scope.allowed_domains))
    if scope.allowed_content_types:
        filters.append(ContentTypeFilter(allowed_types=scope.allowed_content_types))
    return filters
