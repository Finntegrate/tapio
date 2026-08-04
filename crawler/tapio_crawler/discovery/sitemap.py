"""Sitemap-first URL discovery.

Fetches a source's sitemap(s) directly with the shared rate limiter and
robots handling, rather than through Crawl4AI's ``AsyncUrlSeeder`` -
the installed version does not expose a per-URL ``lastmod`` or a
child-sitemap-fetch count, both of which Requirement 2 needs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx

from tapio_crawler.discovery.rate_limiter import HostRateLimiter

logger = logging.getLogger(__name__)

TOO_MANY_REQUESTS_STATUS = 429
SERVICE_UNAVAILABLE_STATUS = 503
CLIENT_ERROR_STATUS = 400


@dataclass
class SitemapUrlEntry:
    """One URL discovered from a sitemap, with its raw lastmod if present."""

    url: str
    lastmod: datetime | None = None


@dataclass
class SitemapDiscoveryResult:
    """The outcome of fetching and parsing every sitemap for one source."""

    urls: list[SitemapUrlEntry] = field(default_factory=list)
    child_sitemaps_fetched: int = 0
    complete: bool = True


async def discover_sitemap_urls(
    sitemap_urls: list[str],
    *,
    client: httpx.AsyncClient,
    rate_limiter: HostRateLimiter,
    user_agent: str,
    max_child_sitemaps: int = 10_000,
) -> SitemapDiscoveryResult:
    """Fetch every sitemap, following sitemap-index nesting.

    Marks the result ``complete=False`` if any sitemap fails to fetch or
    parse, or if the child-sitemap cap is reached, so a discovery run does
    not claim complete source coverage on a partial failure.
    """
    result = SitemapDiscoveryResult()
    if not sitemap_urls:
        result.complete = False
        return result

    queue = list(sitemap_urls)
    seen: set[str] = set()

    while queue:
        if len(seen) >= max_child_sitemaps:
            logger.warning("Reached child-sitemap fetch cap of %s", max_child_sitemaps)
            result.complete = False
            break
        sitemap_url = queue.pop(0)
        if sitemap_url in seen:
            continue
        seen.add(sitemap_url)

        content = await _fetch_sitemap(
            sitemap_url,
            client=client,
            rate_limiter=rate_limiter,
            user_agent=user_agent,
        )
        if content is None:
            result.complete = False
            continue
        result.child_sitemaps_fetched += 1

        try:
            child_sitemaps, urls = _parse_sitemap(content)
        except ET.ParseError:
            logger.warning("Failed to parse sitemap %s", sitemap_url)
            result.complete = False
            continue

        queue.extend(child_sitemaps)
        result.urls.extend(urls)

    return result


async def _fetch_sitemap(
    sitemap_url: str,
    *,
    client: httpx.AsyncClient,
    rate_limiter: HostRateLimiter,
    user_agent: str,
) -> bytes | None:
    """Fetch one sitemap document, honoring the shared per-host rate limit."""
    await rate_limiter.wait_for_turn()
    try:
        response = await client.get(sitemap_url, headers={"User-Agent": user_agent})
    except httpx.HTTPError:
        logger.warning("Failed to fetch sitemap %s", sitemap_url)
        return None

    if response.status_code in (TOO_MANY_REQUESTS_STATUS, SERVICE_UNAVAILABLE_STATUS):
        rate_limiter.suspend_for_retry_after(response.headers.get("Retry-After"))
        return None
    if response.status_code >= CLIENT_ERROR_STATUS:
        logger.warning(
            "Sitemap fetch for %s returned HTTP %s",
            sitemap_url,
            response.status_code,
        )
        return None
    return response.content


def _parse_sitemap(content: bytes) -> tuple[list[str], list[SitemapUrlEntry]]:
    """Return child-sitemap locations and URL entries from one sitemap document."""
    root = ET.fromstring(content)
    _strip_namespaces(root)

    child_sitemaps = [
        loc.text.strip()
        for sitemap_elem in root.findall(".//sitemap")
        if (loc := sitemap_elem.find("loc")) is not None and loc.text
    ]
    if child_sitemaps:
        return child_sitemaps, []

    urls = [
        SitemapUrlEntry(
            url=loc.text.strip(),
            lastmod=_parse_lastmod(
                lastmod_elem.text
                if (lastmod_elem := url_elem.find("lastmod")) is not None
                else None,
            ),
        )
        for url_elem in root.findall(".//url")
        if (loc := url_elem.find("loc")) is not None and loc.text
    ]
    return [], urls


def _strip_namespaces(root: ET.Element) -> None:
    """Drop XML namespace prefixes so ``findall`` can use bare tag names."""
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]


def _parse_lastmod(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None
