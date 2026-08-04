"""Fetch and parse robots.txt with fail-closed semantics for required sources.

Wraps Python's stdlib ``RobotFileParser`` (which itself would fail open on a
fetch error) so a ``robots_policy: require`` source can tell "no rules found"
apart from "rules could not be confirmed".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
NOT_FOUND_STATUS = 404
CLIENT_ERROR_STATUS = 400


@dataclass
class RobotsRules:
    """Parsed robots.txt rules for one host, or an explicit fetch failure.

    ``reachable`` is ``False`` only when the fetch itself failed (network
    error, timeout, or a non-2xx/404 response) - not when robots.txt is
    simply absent, which conventionally means no restrictions.
    """

    reachable: bool
    crawl_delay: float | None = None
    sitemap_urls: list[str] = field(default_factory=list)
    _parser: RobotFileParser | None = None

    def can_fetch(self, user_agent: str, url: str) -> bool:
        """Return whether ``user_agent`` may fetch ``url`` under these rules.

        Callers with ``robots_policy: require`` must check ``reachable``
        first: an unreachable result has no rules to evaluate and must not
        be treated as an implicit allow.
        """
        if self._parser is None:
            return True
        return self._parser.can_fetch(user_agent, url)


async def fetch_robots_rules(
    base_url: str,
    user_agent: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> RobotsRules:
    """Fetch and parse ``base_url``'s robots.txt.

    A 404 means no restrictions, per convention. Any other failure - a
    non-2xx/404 status, a timeout, or a connection error - is reported as
    ``reachable=False``.
    """
    robots_url = urljoin(base_url, "/robots.txt")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await http_client.get(robots_url, headers={"User-Agent": user_agent})
    except httpx.HTTPError:
        logger.warning("Failed to fetch robots.txt from %s", robots_url)
        return RobotsRules(reachable=False)
    finally:
        if owns_client:
            await http_client.aclose()

    if response.status_code == NOT_FOUND_STATUS:
        return RobotsRules(reachable=True)
    if response.status_code >= CLIENT_ERROR_STATUS:
        logger.warning(
            "robots.txt fetch for %s returned HTTP %s",
            robots_url,
            response.status_code,
        )
        return RobotsRules(reachable=False)

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return RobotsRules(
        reachable=True,
        crawl_delay=_own_or_wildcard_crawl_delay(parser, user_agent),
        sitemap_urls=list(parser.site_maps() or []),
        _parser=parser,
    )


def _own_or_wildcard_crawl_delay(
    parser: RobotFileParser,
    user_agent: str,
) -> float | None:
    """Prefer a Crawl-delay stanza for our own User-Agent over a wildcard one."""
    return _safe_crawl_delay(parser, user_agent) or _safe_crawl_delay(parser, "*")


def _safe_crawl_delay(parser: RobotFileParser, user_agent: str) -> float | None:
    """Return a parsed Crawl-delay, ignoring a malformed or missing value."""
    try:
        delay = parser.crawl_delay(user_agent)
        return float(delay) if delay is not None else None
    except ValueError, TypeError:
        return None
