"""A per-host rate limiter shared across every discovery-time request type.

Enforces a source's ``Crawl-delay`` floor under its configured delay window
and treats a ``429``/``503`` ``Retry-After`` as extending the same per-host
suspension for every pending and future request, not just the retried URL.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

DEFAULT_MAX_SUSPENSION_SECONDS = 60 * 60  # 1 hour cap on Retry-After


@dataclass
class EffectiveDelay:
    """The min/max delay window actually used for one host's requests."""

    min_delay: float
    max_delay: float


def resolve_effective_delay(
    *,
    configured_min_delay: float,
    configured_max_delay: float,
    crawl_delay: float | None,
) -> EffectiveDelay:
    """Raise the configured delay window to respect a declared Crawl-delay.

    A successfully parsed ``crawl_delay`` becomes a hard floor under
    ``configured_min_delay``. If that floor would exceed
    ``configured_max_delay``, the maximum is raised to match it (a fixed
    per-host delay, no jitter) instead of producing a negative jitter range.
    A missing ``crawl_delay`` leaves the configured window unchanged.
    """
    if crawl_delay is None:
        return EffectiveDelay(configured_min_delay, configured_max_delay)
    effective_min = max(configured_min_delay, crawl_delay)
    effective_max = max(configured_max_delay, effective_min)
    return EffectiveDelay(effective_min, effective_max)


class HostRateLimiter:
    """Serialize requests to one host behind a shared politeness delay.

    One instance must be shared across every request type against a host -
    robots/sitemap fetches, gap-crawl discovery, rendering, and retries -
    so a ``Retry-After`` suspension or ``Crawl-delay`` floor applies
    uniformly rather than being scoped to one mechanism.
    """

    def __init__(
        self,
        *,
        min_delay: float,
        max_delay: float,
        max_suspension_seconds: float = DEFAULT_MAX_SUSPENSION_SECONDS,
    ) -> None:
        """Initialize the limiter with its politeness delay bounds.

        Args:
            min_delay: Minimum delay, in seconds, between requests to the host.
            max_delay: Maximum delay, in seconds, between requests to the host.
            max_suspension_seconds: Upper bound applied to any ``Retry-After``
                suspension.
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_suspension_seconds = max_suspension_seconds
        self._lock = asyncio.Lock()
        self._next_available_at: float = 0.0
        self.last_suspension_capped = False

    async def wait_for_turn(self) -> None:
        """Block until this host's next request may be sent, then reserve it."""
        async with self._lock:
            wait_seconds = max(0.0, self._next_available_at - time.monotonic())
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._next_available_at = time.monotonic() + self.min_delay

    def suspend_for_retry_after(self, retry_after_value: str | None) -> float:
        """Extend this host's suspension from a 429/503 ``Retry-After`` header.

        Returns the number of seconds actually applied, capped at
        ``max_suspension_seconds``. A missing or unparseable value falls
        back to exponential-backoff-friendly ``max_delay`` instead of a hang
        or an unbounded default; ``last_suspension_capped`` tells the caller
        whether the requested suspension exceeded the cap and pending URLs
        for this host should be marked ``incomplete`` for this run.
        """
        seconds = parse_retry_after(retry_after_value)
        if seconds is None:
            seconds = self.max_delay
            self.last_suspension_capped = False
        else:
            self.last_suspension_capped = seconds > self.max_suspension_seconds
            seconds = min(seconds, self.max_suspension_seconds)
        self._next_available_at = max(
            self._next_available_at,
            time.monotonic() + seconds,
        )
        return seconds


def parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After as delay-seconds or an HTTP-date, per RFC 9110."""
    if not value:
        return None
    stripped = value.strip()
    try:
        return max(0.0, float(stripped))
    except ValueError:
        pass
    try:
        parsed_date = parsedate_to_datetime(stripped)
    except TypeError, ValueError, OverflowError:
        return None
    if parsed_date.tzinfo is None:
        parsed_date = parsed_date.replace(tzinfo=UTC)
    return max(0.0, (parsed_date - datetime.now(UTC)).total_seconds())
