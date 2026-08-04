"""Tests for the shared per-host rate limiter."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from tapio_crawler.discovery.rate_limiter import (
    HostRateLimiter,
    resolve_effective_delay,
)


def test_resolve_effective_delay_without_crawl_delay_keeps_config() -> None:
    delay = resolve_effective_delay(
        configured_min_delay=1.0,
        configured_max_delay=3.0,
        crawl_delay=None,
    )

    assert (delay.min_delay, delay.max_delay) == (1.0, 3.0)


def test_resolve_effective_delay_raises_floor_to_crawl_delay() -> None:
    delay = resolve_effective_delay(
        configured_min_delay=1.0,
        configured_max_delay=3.0,
        crawl_delay=5.0,
    )

    assert delay.min_delay == 5.0
    assert delay.max_delay == 5.0


def test_resolve_effective_delay_keeps_wider_configured_max() -> None:
    delay = resolve_effective_delay(
        configured_min_delay=1.0,
        configured_max_delay=8.0,
        crawl_delay=5.0,
    )

    assert (delay.min_delay, delay.max_delay) == (5.0, 8.0)


def test_resolve_effective_delay_never_produces_negative_range() -> None:
    delay = resolve_effective_delay(
        configured_min_delay=0.0,
        configured_max_delay=0.0,
        crawl_delay=5.0,
    )

    assert delay.max_delay >= delay.min_delay


@pytest.mark.asyncio
async def test_wait_for_turn_serializes_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = HostRateLimiter(min_delay=0.01, max_delay=0.01)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await limiter.wait_for_turn()
    await limiter.wait_for_turn()

    assert len(sleeps) == 1
    assert sleeps[0] > 0


def test_suspend_for_retry_after_parses_delay_seconds() -> None:
    limiter = HostRateLimiter(min_delay=1.0, max_delay=3.0)

    applied = limiter.suspend_for_retry_after("30")

    assert applied == 30.0
    assert limiter.last_suspension_capped is False


def test_suspend_for_retry_after_parses_http_date() -> None:
    limiter = HostRateLimiter(min_delay=1.0, max_delay=3.0)
    future = datetime.now(UTC) + timedelta(seconds=60)

    applied = limiter.suspend_for_retry_after(format_datetime(future, usegmt=True))

    assert applied == pytest.approx(60.0, abs=2.0)


def test_suspend_for_retry_after_falls_back_on_missing_value() -> None:
    limiter = HostRateLimiter(min_delay=1.0, max_delay=3.0)

    applied = limiter.suspend_for_retry_after(None)

    assert applied == 3.0
    assert limiter.last_suspension_capped is False


def test_suspend_for_retry_after_falls_back_on_unparseable_value() -> None:
    limiter = HostRateLimiter(min_delay=1.0, max_delay=3.0)

    applied = limiter.suspend_for_retry_after("not-a-value")

    assert applied == 3.0


def test_suspend_for_retry_after_caps_at_configured_maximum() -> None:
    limiter = HostRateLimiter(min_delay=1.0, max_delay=3.0, max_suspension_seconds=60)

    applied = limiter.suspend_for_retry_after("3600")

    assert applied == 60
    assert limiter.last_suspension_capped is True
