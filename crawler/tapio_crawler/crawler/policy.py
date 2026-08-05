"""Per-document render scheduling and cache-mode selection.

Pure decision logic with no I/O, implementing
docs/specs/crawler-improvements.md's Requirement 5 (per-document cache and
refresh policy): whether a manifest record is due for rendering this run,
and which Crawl4AI ``CacheMode`` to use if so.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from crawl4ai import CacheMode

from tapio_crawler.manifest.models import ManifestRecord

# Bumped whenever the extraction/metadata schema changes materially, so a
# record rendered under an older version is treated as due for a refresh.
EXTRACTOR_VERSION = "2"

# A per-URL retry cap (Requirement 1) is not a configured value - the spec
# does not ask for that as a tunable, so it is a fixed module constant.
MAX_RETRY_COUNT = 5
_BASE_BACKOFF_SECONDS = 3600
_MAX_BACKOFF_SECONDS = 86400


@dataclass
class RenderDecision:
    """Whether one manifest record is due for rendering, and how.

    Attributes:
        cache_mode: The Crawl4AI cache mode to render this URL with.
        reason: Machine-readable reason code, for logging/summary detail.
    """

    cache_mode: CacheMode
    reason: str


def decide_render(  # noqa: PLR0911
    record: ManifestRecord,
    *,
    trust_lastmod: bool,
    unchanged_audit_days: int,
    now: datetime,
    force: bool = False,
) -> RenderDecision | None:
    """Decide whether ``record`` is due for rendering this run, and how.

    One return per due-reason keeps each branch's condition and outcome
    next to each other; splitting it up would trade that clarity for a
    lower branch count.

    Args:
        record: The manifest record to evaluate.
        trust_lastmod: The source's ``discovery.trust_lastmod`` setting -
            whether ``sitemap_lastmod`` may trigger a re-render.
        unchanged_audit_days: The source's ``refresh.unchanged_audit_days``.
        now: The current time (timezone-aware ``datetime``).
        force: When ``True``, ignore the schedule entirely and render.

    Returns:
        A ``RenderDecision`` when the record is due, or ``None`` when it
        should be skipped this run.
    """
    if force:
        return RenderDecision(CacheMode.WRITE_ONLY, "forced")

    if record.retry_after is not None and record.retry_after > now:
        return None

    # A record that has exhausted its retry cap without ever rendering
    # successfully has retry_after=None (backoff no longer applies), but
    # must stay parked rather than falling into "initial_backfill" below
    # and being retried indefinitely every run.
    if record.retry_count > MAX_RETRY_COUNT and record.last_rendered_at is None:
        return None

    if record.last_rendered_at is None:
        return RenderDecision(CacheMode.WRITE_ONLY, "initial_backfill")

    if trust_lastmod and record.sitemap_lastmod and record.sitemap_lastmod > record.last_rendered_at:
        return RenderDecision(CacheMode.WRITE_ONLY, "lastmod_changed")

    if record.extractor_version != EXTRACTOR_VERSION:
        return RenderDecision(CacheMode.ENABLED, "extractor_version_stale")

    audit_anchor = record.last_attempt_at or record.last_rendered_at
    if now >= audit_anchor + timedelta(days=unchanged_audit_days):
        return RenderDecision(CacheMode.ENABLED, "scheduled_audit")

    return None


def retry_backoff_seconds(retry_count: int) -> float:
    """Return the exponential backoff, in seconds, for a URL's next retry.

    Args:
        retry_count: The number of consecutive failed/unconfirmed attempts,
            including the one that just happened.

    Returns:
        The backoff duration, capped at ``_MAX_BACKOFF_SECONDS``.
    """
    return min(_BASE_BACKOFF_SECONDS * (2**retry_count), _MAX_BACKOFF_SECONDS)
