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


class _FakeResult:
    """Stand-in for a crawl4ai crawl result exposing ``url`` and ``success``."""

    def __init__(self, url: str, *, success: bool = True) -> None:
        self.url = url
        self.success = success


class _FakeCrawler:
    """Behaves like AsyncWebCrawler running Crawl4AI's BFS strategy in stream mode.

    For each page it checks ``should_cancel``, yields the result, then reports state
    through ``on_state_change``, and on resume skips the pages ``resume_state`` visited.
    """

    def __init__(self, pages: dict[str, list[_FakeResult]], *, error: Exception | None = None) -> None:
        self.pages = pages
        self.error = error
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.after_page: list[Any] = []

    async def __aenter__(self) -> _FakeCrawler:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def arun(self, url: str, config: Any) -> AsyncIterator[_FakeResult]:
        if self.error is not None:
            raise self.error
        strategy = config.deep_crawl_strategy
        resume = strategy._resume_state
        self.calls.append((url, resume))
        visited = list((resume or {}).get("visited", []))
        remaining = [page for page in self.pages[url] if page.url not in visited]

        async def stream() -> AsyncIterator[_FakeResult]:
            while remaining:
                if strategy._should_cancel is not None and strategy._should_cancel():
                    return
                page = remaining.pop(0)
                visited.append(page.url)
                yield page
                for hook in self.after_page:
                    hook(page)
                await strategy._on_state_change(
                    {"visited": list(visited), "pending": [p.url for p in remaining], "pages_crawled": len(visited)}
                )

        return stream()


def _pages(seed: str, count: int) -> list[_FakeResult]:
    return [_FakeResult(f"{seed}/{index}") for index in range(count)]


async def _discover(crawler: _FakeCrawler, seeds: list[str], **kwargs: Any) -> Any:
    with patch("tapio_crawler.discovery.gap_crawl.AsyncWebCrawler", return_value=crawler):
        return await discover_via_gap_crawl(
            GapCrawlConfig(enabled=True, seed_urls=seeds),
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
async def test_crawls_each_seed_in_turn_and_collects_successful_urls() -> None:
    a, b = "https://example.com", "https://example.com/other"
    crawler = _FakeCrawler({a: _pages(a, 2), b: _pages(b, 1)})

    result = await _discover(crawler, [a, b])

    assert [url for url, _ in crawler.calls] == [a, b]
    assert result.urls == [f"{a}/0", f"{a}/1", f"{b}/0"]
    assert result.complete is True
    assert result.finished is True


@pytest.mark.asyncio
async def test_failed_pages_are_omitted_and_mark_the_crawl_incomplete() -> None:
    seed = "https://example.com"
    crawler = _FakeCrawler({seed: [_FakeResult(f"{seed}/a"), _FakeResult(f"{seed}/b", success=False)]})

    result = await _discover(crawler, [seed])

    assert result.urls == [f"{seed}/a"]
    assert result.complete is False
    assert result.finished is True  # it ran to the end, so its checkpoint can go


@pytest.mark.asyncio
async def test_a_crawl_error_keeps_the_checkpoint() -> None:
    saved: list[dict[str, Any]] = []
    crawler = _FakeCrawler({}, error=RuntimeError("boom"))

    result = await _discover(crawler, ["https://example.com"], save_checkpoint=saved.append)

    assert result.complete is False
    assert result.finished is False
    assert saved  # saved so a later run can resume


@pytest.mark.asyncio
async def test_progress_reports_pages_visited_and_queued() -> None:
    seed = "https://example.com"
    progress = DiscoveryProgress()
    snapshots: list[tuple[int, int]] = []
    crawler = _FakeCrawler({seed: _pages(seed, 3)})
    crawler.after_page.append(lambda _page: snapshots.append((progress.visited, progress.queued)))

    await _discover(crawler, [seed], progress=progress)

    assert (progress.visited, progress.queued) == (3, 0)
    assert snapshots[1] == (1, 2)  # the state reported after the first page
    assert progress.resumed is False


@pytest.mark.asyncio
async def test_a_cancelled_crawl_saves_a_checkpoint_the_next_run_resumes_from() -> None:
    seed = "https://example.com"
    control = JobControl()
    saved: list[dict[str, Any]] = []
    crawler = _FakeCrawler({seed: _pages(seed, 5)})
    crawler.after_page.append(lambda page: control.cancel() if page.url.endswith("/1") else None)

    first = await _discover(crawler, [seed], control=control, save_checkpoint=saved.append)

    assert first.cancelled is True
    assert first.finished is False
    assert first.urls == [f"{seed}/0", f"{seed}/1"]
    checkpoint = saved[-1]
    assert checkpoint["discovered"] == [f"{seed}/0", f"{seed}/1"]

    progress = DiscoveryProgress()
    resumed_crawler = _FakeCrawler({seed: _pages(seed, 5)})
    second = await _discover(resumed_crawler, [seed], checkpoint=checkpoint, progress=progress)

    assert resumed_crawler.calls[0][1] is not None  # Crawl4AI got the saved state back
    assert second.urls == [f"{seed}/{index}" for index in range(5)]
    assert second.finished is True
    assert progress.resumed is True


@pytest.mark.asyncio
async def test_a_resumed_crawl_skips_seeds_that_already_finished() -> None:
    a, b = "https://example.com", "https://example.com/other"
    crawler = _FakeCrawler({a: _pages(a, 2), b: _pages(b, 1)})
    checkpoint = {"seeds": {}, "finished_seeds": [a], "discovered": [f"{a}/0", f"{a}/1"]}

    result = await _discover(crawler, [a, b], checkpoint=checkpoint)

    assert [url for url, _ in crawler.calls] == [b]
    assert result.urls == [f"{a}/0", f"{a}/1", f"{b}/0"]


@pytest.mark.asyncio
async def test_a_pause_holds_the_crawl_between_pages() -> None:
    seed = "https://example.com"
    control = JobControl()
    crawler = _FakeCrawler({seed: _pages(seed, 3)})
    crawler.after_page.append(lambda page: control.pause() if page.url.endswith("/0") else None)

    task = asyncio.create_task(_discover(crawler, [seed], control=control))
    await asyncio.sleep(0.05)
    assert not task.done()  # held after the first page

    control.resume()
    result = await asyncio.wait_for(task, timeout=1)
    assert len(result.urls) == 3
