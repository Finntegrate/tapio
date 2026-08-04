"""Tests for sitemap fetching and parsing."""

import time

import httpx
import pytest

from tapio_crawler.discovery.rate_limiter import HostRateLimiter
from tapio_crawler.discovery.sitemap import discover_sitemap_urls

USER_AGENT = "TapioBot/1.0"

FLAT_URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>https://example.com/b</loc></url>
</urlset>
"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>
</sitemapindex>
"""


def _limiter() -> HostRateLimiter:
    return HostRateLimiter(min_delay=0.0, max_delay=0.0)


@pytest.mark.asyncio
async def test_discovers_urls_and_lastmod_from_flat_urlset() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=FLAT_URLSET)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_sitemap_urls(
            ["https://example.com/sitemap.xml"],
            client=client,
            rate_limiter=_limiter(),
            user_agent=USER_AGENT,
        )

    assert result.complete is True
    assert result.child_sitemaps_fetched == 0
    urls = {entry.url: entry.lastmod for entry in result.urls}
    assert urls["https://example.com/a"] is not None
    assert urls["https://example.com/b"] is None


@pytest.mark.asyncio
async def test_follows_sitemap_index_and_counts_child_sitemaps_separately() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, text=SITEMAP_INDEX)
        return httpx.Response(200, text=FLAT_URLSET)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_sitemap_urls(
            ["https://example.com/sitemap.xml"],
            client=client,
            rate_limiter=_limiter(),
            user_agent=USER_AGENT,
        )

    # The index itself is a top-level entry, not a child; only its 2 children count.
    assert result.child_sitemaps_fetched == 2
    assert len(result.urls) == 4
    assert result.complete is True


@pytest.mark.asyncio
async def test_marks_incomplete_when_a_sitemap_fetch_fails() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_sitemap_urls(
            ["https://example.com/sitemap.xml"],
            client=client,
            rate_limiter=_limiter(),
            user_agent=USER_AGENT,
        )

    assert result.complete is False
    assert result.urls == []


@pytest.mark.asyncio
async def test_marks_incomplete_when_sitemap_is_unparseable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not xml")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_sitemap_urls(
            ["https://example.com/sitemap.xml"],
            client=client,
            rate_limiter=_limiter(),
            user_agent=USER_AGENT,
        )

    assert result.complete is False


@pytest.mark.asyncio
async def test_no_sitemap_urls_is_incomplete() -> None:
    async with httpx.AsyncClient() as client:
        result = await discover_sitemap_urls(
            [],
            client=client,
            rate_limiter=_limiter(),
            user_agent=USER_AGENT,
        )

    assert result.complete is False


@pytest.mark.asyncio
async def test_429_suspends_host_and_marks_incomplete() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "1"})

    transport = httpx.MockTransport(handler)
    limiter = _limiter()
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_sitemap_urls(
            ["https://example.com/sitemap.xml"],
            client=client,
            rate_limiter=limiter,
            user_agent=USER_AGENT,
        )

    assert result.complete is False
    assert limiter.last_suspension_capped is False
    assert limiter._next_available_at > time.monotonic()
