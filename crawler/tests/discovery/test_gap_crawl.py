"""Tests for bounded gap-crawl discovery."""

from unittest.mock import AsyncMock, patch

import pytest

from tapio_crawler.config.config_models import GapCrawlConfig, ScopeConfig
from tapio_crawler.discovery.gap_crawl import discover_via_gap_crawl
from tapio_crawler.discovery.rate_limiter import HostRateLimiter


class _FakeResult:
    """Stand-in for a crawl4ai crawl result exposing ``url`` and ``success``."""

    def __init__(self, url: str, *, success: bool = True) -> None:
        self.url = url
        self.success = success


@pytest.mark.asyncio
async def test_returns_incomplete_when_gap_crawl_disabled() -> None:
    """A disabled gap-crawl config yields no URLs and an incomplete result."""
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
    """Gap-crawl with no seed URLs configured yields an incomplete result."""
    result = await discover_via_gap_crawl(
        GapCrawlConfig(enabled=True, seed_urls=[]),
        ScopeConfig(),
        user_agent="TapioBot/1.0",
        rate_limiter=HostRateLimiter(min_delay=1.0, max_delay=2.0),
        max_concurrent=2,
    )

    assert result.complete is False


@pytest.mark.asyncio
async def test_collects_successful_urls_from_crawl() -> None:
    """Only URLs from successful crawl results are collected."""
    fake_results = [
        _FakeResult("https://example.com/a"),
        _FakeResult("https://example.com/b", success=False),
    ]

    mock_crawler = AsyncMock()
    mock_crawler.arun_many = AsyncMock(return_value=fake_results)
    mock_crawler.__aenter__.return_value = mock_crawler
    mock_crawler.__aexit__.return_value = False

    with patch(
        "tapio_crawler.discovery.gap_crawl.AsyncWebCrawler",
        return_value=mock_crawler,
    ):
        result = await discover_via_gap_crawl(
            GapCrawlConfig(
                enabled=True,
                seed_urls=["https://example.com", "https://example.com/other"],
            ),
            ScopeConfig(allowed_domains=["example.com"]),
            user_agent="TapioBot/1.0",
            rate_limiter=HostRateLimiter(min_delay=1.0, max_delay=2.0),
            max_concurrent=2,
        )

    assert result.complete is True
    assert result.urls == ["https://example.com/a"]
    mock_crawler.arun_many.assert_awaited_once()
    called_urls = mock_crawler.arun_many.call_args.args[0]
    assert called_urls == ["https://example.com", "https://example.com/other"]


@pytest.mark.asyncio
async def test_marks_incomplete_on_crawl_exception() -> None:
    """An exception raised by the crawler marks the result incomplete."""
    mock_crawler = AsyncMock()
    mock_crawler.arun_many = AsyncMock(side_effect=RuntimeError("boom"))
    mock_crawler.__aenter__.return_value = mock_crawler
    mock_crawler.__aexit__.return_value = False

    with patch(
        "tapio_crawler.discovery.gap_crawl.AsyncWebCrawler",
        return_value=mock_crawler,
    ):
        result = await discover_via_gap_crawl(
            GapCrawlConfig(enabled=True, seed_urls=["https://example.com"]),
            ScopeConfig(),
            user_agent="TapioBot/1.0",
            rate_limiter=HostRateLimiter(min_delay=1.0, max_delay=2.0),
            max_concurrent=2,
        )

    assert result.complete is False
