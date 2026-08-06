"""Tests for robots.txt fetching and fail-closed parsing."""

import httpx
import pytest

from tapio_crawler.discovery.robots import fetch_robots_rules

USER_AGENT = "TapioBot/1.0 (+https://github.com/Finntegrate/tapio)"


@pytest.mark.asyncio
async def test_missing_robots_txt_is_reachable_with_no_restrictions() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.reachable is True
    assert rules.crawl_delay is None
    assert rules.can_fetch(USER_AGENT, "https://example.com/anything") is True


@pytest.mark.asyncio
async def test_server_error_is_reported_unreachable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.reachable is False


@pytest.mark.asyncio
async def test_connection_error_is_reported_unreachable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        msg = "boom"
        raise httpx.ConnectError(msg, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.reachable is False


@pytest.mark.asyncio
async def test_own_user_agent_crawl_delay_takes_precedence_over_wildcard() -> None:
    # robots.txt conventionally names a bot by its short product token, not
    # the full descriptive User-Agent header string sent in requests.
    body = "User-agent: TapioBot\nCrawl-delay: 5\n\nUser-agent: *\nCrawl-delay: 1\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.reachable is True
    assert rules.crawl_delay == 5.0


@pytest.mark.asyncio
async def test_falls_back_to_wildcard_crawl_delay() -> None:
    body = "User-agent: *\nCrawl-delay: 2\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.crawl_delay == 2.0


@pytest.mark.asyncio
async def test_non_numeric_crawl_delay_is_ignored() -> None:
    body = "User-agent: *\nCrawl-delay: soon\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.crawl_delay is None


@pytest.mark.asyncio
async def test_disallowed_path_is_reported() -> None:
    body = "User-agent: TapioBot\nDisallow: /private/\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.can_fetch(USER_AGENT, "https://example.com/private/page") is False
    assert rules.can_fetch(USER_AGENT, "https://example.com/public/page") is True


@pytest.mark.asyncio
async def test_records_the_fetched_robots_txt_url() -> None:
    """The resolved robots.txt URL is recorded, on both success and failure,
    so a discovery run can report which URL it actually used.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.url == "https://example.com/robots.txt"


@pytest.mark.asyncio
async def test_records_the_attempted_robots_txt_url_on_failure() -> None:
    """An unreachable robots.txt still records the URL that was attempted."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.reachable is False
    assert rules.url == "https://example.com/robots.txt"


@pytest.mark.asyncio
async def test_extracts_sitemap_urls() -> None:
    body = "Sitemap: https://example.com/sitemap.xml\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        rules = await fetch_robots_rules(
            "https://example.com",
            USER_AGENT,
            client=client,
        )

    assert rules.sitemap_urls == ["https://example.com/sitemap.xml"]
