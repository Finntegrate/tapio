"""Tests for bounded gap-crawl discovery, including checkpoint and resume (#178)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest

from tapio_crawler.config.config_models import GapCrawlConfig, ScopeConfig
from tapio_crawler.crawler.job_control import DiscoveryProgress, JobControl
from tapio_crawler.discovery.gap_crawl import discover_via_gap_crawl
from tapio_crawler.discovery.rate_limiter import HostRateLimiter

ROOT = "https://example.com"


class _FakeResult:
    """Stand-in for a crawl4ai crawl result exposing ``url`` and ``success``."""

    def __init__(self, url: str, *, success: bool = True) -> None:
        self.url = url
        self.success = success


class _FakeCrawler:
    """Replays Crawl4AI 0.9.2's BFS stream mode (``BFSDeepCrawlStrategy._arun_stream``) over a link graph.

    Kept faithful to the parts the checkpoint logic depends on: a link is added to
    ``visited`` when it is queued, not when it is crawled; ``pending`` holds only the next
    level; cancellation is checked only between levels; the page that reaches
    ``max_pages`` is dropped before it is yielded; and pages are fetched lazily, so
    closing the stream fetches nothing more.
    """

    def __init__(
        self,
        links: dict[str, list[str]],
        *,
        failing: frozenset[str] = frozenset(),
        crash_on: str | None = None,
    ) -> None:
        self.links = links
        self.failing = failing
        self.crash_on = crash_on
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.fetched: list[str] = []
        self.after_page: list[Any] = []
        self.on_fetch: list[Any] = []

    async def __aenter__(self) -> _FakeCrawler:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def arun(self, url: str, config: Any) -> AsyncIterator[_FakeResult]:
        strategy = config.deep_crawl_strategy
        self.calls.append((url, strategy._resume_state))
        return self._bfs(url, strategy)

    async def _bfs(self, start: str, strategy: Any) -> AsyncIterator[_FakeResult]:  # noqa: C901, PLR0912 - mirrors Crawl4AI
        resume = strategy._resume_state
        if resume:
            visited = set(resume["visited"])
            level = [item["url"] for item in resume["pending"]]
            depths = dict(resume["depths"])
            crawled = resume["pages_crawled"]
        else:
            visited, level, depths, crawled = set(), [start], {start: 0}, 0

        def state(pending: list[str], *, cancelled: bool = False) -> dict[str, Any]:
            return {
                "strategy_type": "bfs",
                "visited": sorted(visited),
                "pending": [{"url": url, "parent_url": None} for url in pending],
                "depths": dict(depths),
                "pages_crawled": crawled,
                "cancelled": cancelled,
            }

        cancelled = False
        while level:
            if strategy._should_cancel is not None and strategy._should_cancel():
                cancelled = True
                break
            next_level: list[str] = []
            for url in level:
                if url == self.crash_on:
                    msg = "browser crashed"
                    raise RuntimeError(msg)
                self.fetched.append(url)
                for hook in self.on_fetch:
                    hook(url)
                success = url not in self.failing
                if success:
                    crawled += 1
                    if crawled >= strategy.max_pages:
                        return  # Crawl4AI 0.9.2 drops this result before yielding it
                yield _FakeResult(url, success=success)
                for hook in self.after_page:
                    hook(url)
                if success:
                    if depths[url] < strategy.max_depth:
                        for link in self.links.get(url, []):
                            if link not in visited:
                                visited.add(link)
                                depths[link] = depths[url] + 1
                                next_level.append(link)
                    await strategy._on_state_change(state(next_level))
            level = next_level
        if cancelled:
            await strategy._on_state_change(state(level, cancelled=True))


# ROOT links to four pages, each of which links to two more: 13 pages over three levels.
SITE = {ROOT: [f"{ROOT}/{c}" for c in "abcd"]} | {f"{ROOT}/{c}": [f"{ROOT}/{c}/1", f"{ROOT}/{c}/2"] for c in "abcd"}
ALL_PAGES = {ROOT, *SITE[ROOT], *(child for c in "abcd" for child in SITE[f"{ROOT}/{c}"])}


async def _discover(crawler: _FakeCrawler, seeds: list[str], *, max_pages: int = 100, **kwargs: Any) -> Any:
    with patch("tapio_crawler.discovery.gap_crawl.AsyncWebCrawler", return_value=crawler):
        return await discover_via_gap_crawl(
            GapCrawlConfig(enabled=True, seed_urls=seeds, max_depth=5, max_pages=max_pages),
            ScopeConfig(allowed_domains=["example.com"]),
            user_agent="TapioBot/1.0",
            rate_limiter=HostRateLimiter(min_delay=0.0, max_delay=0.0),
            max_concurrent=2,
            **kwargs,
        )


@pytest.mark.asyncio
async def test_returns_incomplete_when_gap_crawl_disabled() -> None:
    result = await discover_via_gap_crawl(
        GapCrawlConfig(enabled=False),
        ScopeConfig(),
        user_agent="TapioBot/1.0",
        rate_limiter=HostRateLimiter(min_delay=1.0, max_delay=2.0),
        max_concurrent=2,
    )

    assert result.complete is False
    assert result.urls == []


@pytest.mark.asyncio
async def test_returns_incomplete_when_no_seed_urls() -> None:
    result = await discover_via_gap_crawl(
        GapCrawlConfig(enabled=True, seed_urls=[]),
        ScopeConfig(),
        user_agent="TapioBot/1.0",
        rate_limiter=HostRateLimiter(min_delay=1.0, max_delay=2.0),
        max_concurrent=2,
    )

    assert result.complete is False


@pytest.mark.asyncio
async def test_crawls_each_seed_in_turn_and_collects_every_page() -> None:
    other = "https://example.org"
    crawler = _FakeCrawler(SITE | {other: [f"{other}/x"]})

    result = await _discover(crawler, [ROOT, other])

    assert [url for url, _ in crawler.calls] == [ROOT, other]
    assert set(result.urls) == ALL_PAGES | {other, f"{other}/x"}
    assert result.complete is True
    assert result.finished is True


@pytest.mark.asyncio
async def test_failed_pages_are_omitted_and_mark_the_crawl_incomplete() -> None:
    crawler = _FakeCrawler(SITE, failing=frozenset({f"{ROOT}/b"}))

    result = await _discover(crawler, [ROOT])

    assert f"{ROOT}/b" not in result.urls
    assert result.complete is False
    assert result.finished is True  # it ran to the end, so its checkpoint can go


@pytest.mark.parametrize("max_pages", [1, 3, 5])
@pytest.mark.asyncio
async def test_max_pages_returns_exactly_that_many_pages(max_pages: int) -> None:
    """Crawl4AI's stream drops the page that reaches max_pages; asking for one more cancels that out."""
    result = await _discover(_FakeCrawler(SITE), [ROOT], max_pages=max_pages)

    assert len(result.urls) == max_pages


@pytest.mark.asyncio
async def test_a_cancel_mid_level_stops_fetching_and_resumes_without_losing_pages() -> None:
    """The checkpoint is the last level boundary, so the interrupted level is redone, not skipped."""
    control = JobControl()
    saved: list[dict[str, Any]] = []
    crawler = _FakeCrawler(SITE)
    crawler.on_fetch.append(lambda url: control.cancel() if url == f"{ROOT}/b" else None)

    first = await _discover(crawler, [ROOT], control=control, save_checkpoint=saved.append)

    assert first.cancelled is True
    assert crawler.fetched == [ROOT, f"{ROOT}/a", f"{ROOT}/b"]  # c and d never requested
    resumable = saved[-1]["seeds"][ROOT]
    assert [item["url"] for item in resumable["pending"]] == SITE[ROOT]  # the whole level, not just a's children

    progress = DiscoveryProgress()
    resumed_crawler = _FakeCrawler(SITE)
    second = await _discover(resumed_crawler, [ROOT], checkpoint=saved[-1], progress=progress)

    assert set(second.urls) == ALL_PAGES
    assert len(second.urls) == len(ALL_PAGES)  # pages redone after the resume aren't duplicated
    assert ROOT not in resumed_crawler.fetched  # the finished level isn't redone
    assert second.finished is True
    assert progress.resumed is True


@pytest.mark.asyncio
async def test_a_crash_mid_level_keeps_a_checkpoint_that_resumes_every_page() -> None:
    saved: list[dict[str, Any]] = []

    crashed = await _discover(_FakeCrawler(SITE, crash_on=f"{ROOT}/b/1"), [ROOT], save_checkpoint=saved.append)

    assert crashed.finished is False
    assert crashed.complete is False
    second = await _discover(_FakeCrawler(SITE), [ROOT], checkpoint=saved[-1])
    assert set(second.urls) == ALL_PAGES


@pytest.mark.asyncio
async def test_a_failure_before_a_cancel_still_marks_the_resumed_crawl_incomplete() -> None:
    control = JobControl()
    saved: list[dict[str, Any]] = []
    crawler = _FakeCrawler(SITE, failing=frozenset({f"{ROOT}/a"}))
    crawler.after_page.append(lambda url: control.cancel() if url == f"{ROOT}/b" else None)
    await _discover(crawler, [ROOT], control=control, save_checkpoint=saved.append)

    resumed = await _discover(_FakeCrawler(SITE), [ROOT], checkpoint=saved[-1])

    assert resumed.complete is False


@pytest.mark.asyncio
async def test_progress_counts_pages_crawled_not_links_queued() -> None:
    progress = DiscoveryProgress()
    snapshots: list[tuple[int, int]] = []
    crawler = _FakeCrawler(SITE)
    crawler.after_page.append(lambda _url: snapshots.append((progress.visited, progress.queued)))

    await _discover(crawler, [ROOT], progress=progress)

    assert snapshots[1] == (1, 4)  # after the root page: one page crawled, its four links queued
    assert progress.visited == len(ALL_PAGES)
    assert progress.resumed is False


@pytest.mark.asyncio
async def test_a_resumed_crawl_skips_seeds_that_already_finished() -> None:
    other = "https://example.org"
    crawler = _FakeCrawler({other: []})
    checkpoint = {"seeds": {}, "finished_seeds": [ROOT], "discovered": [ROOT], "all_succeeded": True}

    result = await _discover(crawler, [ROOT, other], checkpoint=checkpoint)

    assert [url for url, _ in crawler.calls] == [other]
    assert result.urls == [ROOT, other]


@pytest.mark.asyncio
async def test_a_pause_holds_the_crawl_between_pages() -> None:
    control = JobControl()
    crawler = _FakeCrawler(SITE)
    crawler.after_page.append(lambda url: control.pause() if url == ROOT else None)

    task = asyncio.create_task(_discover(crawler, [ROOT], control=control))
    await asyncio.sleep(0.05)
    assert not task.done()
    assert crawler.fetched == [ROOT]  # held after the first page

    control.resume()
    result = await asyncio.wait_for(task, timeout=1)
    assert set(result.urls) == ALL_PAGES
