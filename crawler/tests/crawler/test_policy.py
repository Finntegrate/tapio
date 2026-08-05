"""Tests for per-document render scheduling and cache-mode selection."""

from datetime import UTC, datetime, timedelta

from crawl4ai import CacheMode

from tapio_crawler.crawler.policy import (
    EXTRACTOR_VERSION,
    MAX_RETRY_COUNT,
    decide_render,
    retry_backoff_seconds,
)
from tapio_crawler.manifest.models import ManifestRecord

NOW = datetime(2026, 8, 5, tzinfo=UTC)


def _record(**overrides: object) -> ManifestRecord:
    defaults: dict[str, object] = {
        "site_name": "example",
        "source_url": "https://example.com/a",
        "canonical_url": "https://example.com/a",
        "first_seen_at": NOW - timedelta(days=200),
        "last_seen_at": NOW,
        "scope_status": "eligible",
    }
    defaults.update(overrides)
    return ManifestRecord(**defaults)


def test_never_rendered_is_due_write_only() -> None:
    """A record with no prior render is due for an initial backfill."""
    record = _record()

    decision = decide_render(record, trust_lastmod=False, unchanged_audit_days=90, now=NOW)

    assert decision is not None
    assert decision.cache_mode is CacheMode.WRITE_ONLY
    assert decision.reason == "initial_backfill"


def test_trusted_lastmod_newer_than_render_is_due_write_only() -> None:
    """A newer sitemap lastmod triggers a re-render only when trusted."""
    record = _record(
        last_rendered_at=NOW - timedelta(days=10),
        last_attempt_at=NOW - timedelta(days=10),
        extractor_version=EXTRACTOR_VERSION,
        sitemap_lastmod=NOW - timedelta(days=1),
    )

    decision = decide_render(record, trust_lastmod=True, unchanged_audit_days=90, now=NOW)

    assert decision is not None
    assert decision.cache_mode is CacheMode.WRITE_ONLY
    assert decision.reason == "lastmod_changed"


def test_untrusted_lastmod_does_not_trigger_render() -> None:
    """A newer lastmod is ignored when the source's trust_lastmod is False."""
    record = _record(
        last_rendered_at=NOW - timedelta(days=10),
        last_attempt_at=NOW - timedelta(days=10),
        extractor_version=EXTRACTOR_VERSION,
        sitemap_lastmod=NOW - timedelta(days=1),
    )

    decision = decide_render(record, trust_lastmod=False, unchanged_audit_days=90, now=NOW)

    assert decision is None


def test_stale_extractor_version_is_due_enabled() -> None:
    """A record rendered under an older extractor version is due for refresh."""
    record = _record(
        last_rendered_at=NOW - timedelta(days=1),
        last_attempt_at=NOW - timedelta(days=1),
        extractor_version="1",
    )

    decision = decide_render(record, trust_lastmod=False, unchanged_audit_days=90, now=NOW)

    assert decision is not None
    assert decision.cache_mode is CacheMode.ENABLED
    assert decision.reason == "extractor_version_stale"


def test_scheduled_audit_due_after_unchanged_audit_days() -> None:
    """A record is due for a scheduled check once its audit window elapses."""
    record = _record(
        last_rendered_at=NOW - timedelta(days=91),
        last_attempt_at=NOW - timedelta(days=91),
        extractor_version=EXTRACTOR_VERSION,
    )

    decision = decide_render(record, trust_lastmod=False, unchanged_audit_days=90, now=NOW)

    assert decision is not None
    assert decision.cache_mode is CacheMode.ENABLED
    assert decision.reason == "scheduled_audit"


def test_not_due_before_unchanged_audit_days_elapses() -> None:
    """A recently rendered, up-to-date record is not due yet."""
    record = _record(
        last_rendered_at=NOW - timedelta(days=1),
        last_attempt_at=NOW - timedelta(days=1),
        extractor_version=EXTRACTOR_VERSION,
    )

    decision = decide_render(record, trust_lastmod=False, unchanged_audit_days=90, now=NOW)

    assert decision is None


def test_future_retry_after_is_not_due() -> None:
    """A record still backing off from a prior failure is skipped."""
    record = _record(retry_after=NOW + timedelta(hours=1))

    decision = decide_render(record, trust_lastmod=False, unchanged_audit_days=90, now=NOW)

    assert decision is None


def test_force_overrides_schedule_and_backoff() -> None:
    """``force=True`` renders even a not-yet-due or backing-off record."""
    record = _record(
        last_rendered_at=NOW - timedelta(days=1),
        last_attempt_at=NOW - timedelta(days=1),
        extractor_version=EXTRACTOR_VERSION,
        retry_after=NOW + timedelta(hours=1),
    )

    decision = decide_render(record, trust_lastmod=False, unchanged_audit_days=90, now=NOW, force=True)

    assert decision is not None
    assert decision.cache_mode is CacheMode.WRITE_ONLY
    assert decision.reason == "forced"


def test_retry_backoff_grows_exponentially_and_is_capped() -> None:
    """Backoff doubles per retry, capped at 24 hours."""
    assert retry_backoff_seconds(1) == 3600 * 2
    assert retry_backoff_seconds(2) == 3600 * 4
    assert retry_backoff_seconds(MAX_RETRY_COUNT) <= 86400
    assert retry_backoff_seconds(MAX_RETRY_COUNT + 5) == 86400
