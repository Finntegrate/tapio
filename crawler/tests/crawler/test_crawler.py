"""Tests for the manifest-driven Crawl4AI renderer."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import frontmatter
import pytest
from pydantic import HttpUrl

from tapio_crawler.config.config_models import CrawlerConfig, ScopeConfig, SiteConfig
from tapio_crawler.crawler.crawler import Crawl4AICrawler, RenderRunSummary
from tapio_crawler.crawler.job_control import JobControl, SiteProgress
from tapio_crawler.crawler.policy import EXTRACTOR_VERSION, MAX_RETRY_COUNT
from tapio_crawler.discovery.rate_limiter import HostRateLimiter
from tapio_crawler.discovery.robots import RobotsRules
from tapio_crawler.manifest.models import ManifestRecord
from tapio_crawler.manifest.normalize import canonicalize_url
from tapio_crawler.manifest.store import ManifestStore


def site_config(**overrides: object) -> SiteConfig:
    scope = overrides.pop("scope", ScopeConfig(allowed_domains=["example.com"]))
    return SiteConfig(
        base_url=HttpUrl("https://example.com"),
        crawler_config=CrawlerConfig(min_delay=0, max_delay=0, scope=scope, **overrides),
    )


def raw_result(
    *,
    success: bool = True,
    markdown: str = "Useful content " * 20,
    url: str = "https://example.com/permit",
    status_code: int | None = 200,
    cache_status: str = "miss",
    response_headers: dict[str, str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        success=success,
        markdown=SimpleNamespace(fit_markdown=markdown),
        metadata={"url": url, "title": "Residence permit"},
        url=url,
        status_code=status_code,
        cache_status=cache_status,
        response_headers=response_headers or {},
        error_message="failed" if not success else None,
    )


def seed_record(store: ManifestStore, **overrides: object) -> ManifestRecord:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "site_name": "example",
        "source_url": "https://example.com/permit",
        "canonical_url": "https://example.com/permit",
        "first_seen_at": now - timedelta(days=200),
        "last_seen_at": now,
        "scope_status": "eligible",
    }
    defaults.update(overrides)
    record = ManifestRecord(**defaults)
    store.upsert(record)
    return record


def mock_browser(*, arun_results: list[object] | None = None, side_effect: object = None) -> MagicMock:
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(return_value=browser)
    browser.__aexit__ = AsyncMock(return_value=None)
    if side_effect is not None:
        browser.arun = AsyncMock(side_effect=side_effect)
    else:
        browser.arun = AsyncMock(return_value=arun_results or [raw_result()])
    return browser


async def _run(
    store: ManifestStore,
    content_dir: Path,
    *,
    config: SiteConfig | None = None,
    browser: MagicMock | None = None,
    max_urls: int = 5_000,
    batch_size: int = 500,
    force: bool = False,
    **crawl_options: object,
) -> RenderRunSummary:
    with (
        patch(
            "tapio_crawler.crawler.crawler.fetch_robots_rules",
            AsyncMock(return_value=RobotsRules(reachable=True)),
        ),
        patch(
            "tapio_crawler.crawler.crawler.AsyncWebCrawler",
            return_value=browser or mock_browser(),
        ),
        patch("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", content_dir),
    ):
        crawler = Crawl4AICrawler("example", config or site_config(), store)
        return await crawler.crawl(max_urls=max_urls, batch_size=batch_size, force=force, **crawl_options)


@pytest.mark.asyncio
async def test_initial_backfill_writes_frontmatter_keyed_by_canonical_url(
    tmp_path: Path,
) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    summary = await _run(store, tmp_path)
    store.close()

    assert summary.saved == 1
    assert summary.complete is True
    digest = hashlib.sha256(b"https://example.com/permit").hexdigest()[:12]
    output = tmp_path / "example" / "parsed" / f"permit-{digest}.md"
    document = frontmatter.load(output)
    assert document.metadata["canonical_url"] == "https://example.com/permit"
    assert document.metadata["extractor_version"] == EXTRACTOR_VERSION
    assert document.metadata["language"] is None
    assert "content_hash" in document.metadata


@pytest.mark.asyncio
async def test_resumability_skips_record_not_yet_due(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    now = datetime.now(UTC)
    seed_record(
        store,
        last_rendered_at=now - timedelta(days=1),
        last_attempt_at=now - timedelta(days=1),
        extractor_version=EXTRACTOR_VERSION,
        fetch_status="success",
    )
    browser = mock_browser()

    summary = await _run(store, tmp_path, browser=browser)
    store.close()

    browser.arun.assert_not_called()
    assert summary.considered == 1
    assert summary.skipped_not_due == 1
    assert summary.saved == 0
    assert summary.current_total == 1
    assert summary.coverage_percent == 100.0


@pytest.mark.asyncio
async def test_force_renders_a_record_that_is_not_due(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    now = datetime.now(UTC)
    seed_record(
        store,
        last_rendered_at=now - timedelta(days=1),
        last_attempt_at=now - timedelta(days=1),
        extractor_version=EXTRACTOR_VERSION,
        fetch_status="success",
    )

    summary = await _run(store, tmp_path, force=True)

    assert summary.saved == 1
    store.close()


@pytest.mark.asyncio
async def test_hit_validated_confirms_without_advancing_last_rendered_at(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    now = datetime.now(UTC)
    rendered_at = now - timedelta(days=91)
    seed_record(
        store,
        last_rendered_at=rendered_at,
        last_attempt_at=rendered_at,
        extractor_version=EXTRACTOR_VERSION,
        fetch_status="success",
    )
    browser = mock_browser(arun_results=[raw_result(cache_status="hit_validated")])

    await _run(store, tmp_path, browser=browser)

    updated = store.get("example", "https://example.com/permit")
    store.close()
    assert updated is not None
    assert updated.validation_status == "confirmed"
    assert updated.last_rendered_at == rendered_at


@pytest.mark.asyncio
async def test_hit_fallback_marks_unconfirmed_and_schedules_retry(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    now = datetime.now(UTC)
    rendered_at = now - timedelta(days=91)
    seed_record(
        store,
        last_rendered_at=rendered_at,
        last_attempt_at=rendered_at,
        extractor_version=EXTRACTOR_VERSION,
        fetch_status="success",
    )
    browser = mock_browser(arun_results=[raw_result(cache_status="hit_fallback")])

    summary = await _run(store, tmp_path, browser=browser)

    updated = store.get("example", "https://example.com/permit")
    store.close()
    assert updated is not None
    assert updated.validation_status == "unconfirmed"
    assert updated.last_rendered_at == rendered_at
    assert updated.retry_after is not None
    assert updated.retry_after > now
    assert summary.retried == 1


@pytest.mark.asyncio
async def test_render_failure_schedules_exponential_backoff(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    browser = mock_browser(arun_results=[raw_result(success=False, status_code=500)])

    summary = await _run(store, tmp_path, browser=browser)

    updated = store.get("example", "https://example.com/permit")
    store.close()
    assert updated is not None
    assert updated.fetch_status == "failed"
    assert updated.retry_count == 1
    assert updated.retry_after is not None
    assert summary.failed == 1


@pytest.mark.asyncio
async def test_retry_cap_stops_scheduling_further_retries(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store, retry_count=MAX_RETRY_COUNT, fetch_status="failed")
    browser = mock_browser(arun_results=[raw_result(success=False, status_code=500)])

    await _run(store, tmp_path, browser=browser, force=True)

    updated = store.get("example", "https://example.com/permit")
    assert updated is not None
    assert updated.retry_count == MAX_RETRY_COUNT + 1
    assert updated.retry_after is None

    # A record that exhausted its retry cap without ever rendering
    # successfully must stay parked on a later, non-forced run rather than
    # being immediately re-selected as an "initial backfill".
    second_browser = mock_browser()
    summary = await _run(store, tmp_path, browser=second_browser)
    store.close()

    second_browser.arun.assert_not_called()
    assert summary.considered == 1
    assert summary.skipped_not_due == 1
    assert summary.saved == 0


@pytest.mark.asyncio
async def test_429_extends_shared_host_suspension(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    browser = mock_browser(
        arun_results=[
            raw_result(success=False, status_code=429, response_headers={"Retry-After": "120"}),
        ],
    )

    with patch("tapio_crawler.crawler.crawler.HostRateLimiter.suspend_for_retry_after") as suspend:
        await _run(store, tmp_path, browser=browser)

    store.close()
    suspend.assert_called_once_with("120")


@pytest.mark.asyncio
async def test_redirect_to_different_canonical_url_rekeys_manifest_and_artifact(
    tmp_path: Path,
) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store, source_url="https://example.com/old-permit", canonical_url="https://example.com/old-permit")
    browser = mock_browser(arun_results=[raw_result(url="https://example.com/new-permit")])

    summary = await _run(store, tmp_path, browser=browser)

    assert summary.saved == 1
    old = store.get("example", "https://example.com/old-permit")
    new = store.get("example", canonicalize_url("https://example.com/new-permit"))
    store.close()
    assert old is None
    assert new is not None
    assert new.canonical_url == "https://example.com/new-permit"

    old_digest = hashlib.sha256(b"https://example.com/old-permit").hexdigest()[:12]
    new_digest = hashlib.sha256(b"https://example.com/new-permit").hexdigest()[:12]
    assert not (tmp_path / "example" / "parsed" / f"old-permit-{old_digest}.md").exists()
    assert (tmp_path / "example" / "parsed" / f"new-permit-{new_digest}.md").exists()


@pytest.mark.asyncio
async def test_out_of_scope_redirect_is_discarded_not_saved(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    browser = mock_browser(arun_results=[raw_result(url="https://evil.example/permit")])

    summary = await _run(store, tmp_path, browser=browser)

    updated = store.get("example", "https://example.com/permit")
    store.close()
    assert summary.saved == 0
    assert summary.failed == 1
    assert updated is not None
    assert updated.fetch_status == "failed"


@pytest.mark.asyncio
async def test_near_empty_result_retries_and_recovers(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    browser = mock_browser(
        side_effect=[[raw_result(markdown="short")], [raw_result()]],
    )

    summary = await _run(store, tmp_path, browser=browser)

    store.close()
    assert summary.low_quality == 1
    assert summary.saved == 1
    fallback_config = browser.arun.await_args_list[1].kwargs["config"]
    assert fallback_config.css_selector is None
    assert fallback_config.cache_mode.name == "WRITE_ONLY"


@pytest.mark.asyncio
async def test_near_empty_result_unrecoverable_marks_failure(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    browser = mock_browser(
        side_effect=[[raw_result(markdown="short")], [raw_result(markdown="short")]],
    )

    summary = await _run(store, tmp_path, browser=browser)

    store.close()
    assert summary.low_quality == 1
    assert summary.saved == 0
    assert summary.failed == 1


@pytest.mark.asyncio
async def test_robots_required_and_unreachable_marks_run_incomplete(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)

    with (
        patch(
            "tapio_crawler.crawler.crawler.fetch_robots_rules",
            AsyncMock(return_value=RobotsRules(reachable=False)),
        ),
        patch("tapio_crawler.crawler.crawler.DEFAULT_CONTENT_DIR", tmp_path),
    ):
        crawler = Crawl4AICrawler("example", site_config(), store)
        summary = await crawler.crawl(max_urls=5_000, batch_size=500)

    store.close()
    assert summary.complete is False
    assert summary.rendered == 0


@pytest.mark.asyncio
async def test_no_eligible_records_renders_nothing(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    browser = mock_browser()

    summary = await _run(store, tmp_path, browser=browser)

    store.close()
    browser.arun.assert_not_called()
    assert summary.rendered == 0
    assert summary.saved == 0


@pytest.mark.asyncio
async def test_arun_exception_is_recorded_as_a_failure(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    browser = mock_browser(side_effect=RuntimeError("network error"))

    summary = await _run(store, tmp_path, browser=browser)

    updated = store.get("example", "https://example.com/permit")
    store.close()
    assert summary.saved == 0
    assert updated is not None
    assert updated.fetch_status == "failed"
    assert updated.retry_count == 1


@pytest.mark.asyncio
async def test_browser_launch_failure_marks_run_incomplete(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    browser = MagicMock()
    browser.__aenter__ = AsyncMock(side_effect=RuntimeError("browser unavailable"))

    summary = await _run(store, tmp_path, browser=browser)

    store.close()
    assert summary.complete is False
    assert summary.saved == 0


@pytest.mark.asyncio
async def test_coverage_percent_reflects_manifest_state(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store, canonical_url="https://example.com/a", source_url="https://example.com/a")
    seed_record(store, canonical_url="https://example.com/b", source_url="https://example.com/b")
    browser = mock_browser(arun_results=[raw_result(url="https://example.com/a")])

    summary = await _run(store, tmp_path, browser=browser, max_urls=1, batch_size=1)

    store.close()
    assert summary.eligible_total == 2
    assert summary.current_total == 1
    assert summary.coverage_percent == 50.0


def test_coverage_percent_is_100_when_nothing_is_eligible() -> None:
    """An empty eligible set reports full coverage rather than dividing by zero."""
    summary = RenderRunSummary(run_id="abc", site_name="example")

    assert summary.coverage_percent == 100.0


def test_markdown_prefers_filtered_content() -> None:
    """The filtered ``fit_markdown`` is preferred when it has content."""
    result = SimpleNamespace(markdown=SimpleNamespace(fit_markdown="Filtered", raw_markdown="Raw"))

    assert Crawl4AICrawler._markdown(result) == "Filtered"


def test_markdown_uses_cached_raw_markdown_when_filtered_value_is_empty() -> None:
    """An empty cached ``fit_markdown`` falls back to ``raw_markdown``."""
    result = SimpleNamespace(markdown=SimpleNamespace(fit_markdown="", raw_markdown="Cached document content"))

    assert Crawl4AICrawler._markdown(result) == "Cached document content"


def test_markdown_returns_empty_string_when_markdown_is_none() -> None:
    """A missing ``markdown`` field yields an empty string rather than an error."""
    result = SimpleNamespace(markdown=None)

    assert Crawl4AICrawler._markdown(result) == ""


def test_filename_includes_normalized_query_in_stem() -> None:
    """A canonical URL's query string becomes part of the filename stem."""
    filename = Crawl4AICrawler._filename("https://example.com/permit?id=1")

    assert filename.startswith("permit-id-1-")


def test_filename_differs_for_different_canonical_urls() -> None:
    """Two distinct canonical URLs never collide on the same filename."""
    assert Crawl4AICrawler._filename("https://example.com/a") != Crawl4AICrawler._filename("https://example.com/b")


@pytest.mark.asyncio
async def test_cancelled_control_renders_nothing_and_marks_run_incomplete(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    control = JobControl()
    control.cancel()
    browser = mock_browser()

    summary = await _run(store, tmp_path, browser=browser, control=control)

    store.close()
    assert summary.cancelled
    assert not summary.complete
    assert summary.rendered == 0
    browser.arun.assert_not_awaited()


@pytest.mark.asyncio
async def test_paused_control_holds_rendering_until_resumed(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    control = JobControl()
    control.pause()
    browser = mock_browser()

    task = asyncio.ensure_future(_run(store, tmp_path, browser=browser, control=control))
    await asyncio.sleep(0.05)
    assert not task.done()
    browser.arun.assert_not_awaited()

    control.resume()
    summary = await task

    store.close()
    assert summary.saved == 1
    assert summary.complete


@pytest.mark.asyncio
async def test_cancel_releases_a_paused_job(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    control = JobControl()
    control.pause()

    task = asyncio.ensure_future(_run(store, tmp_path, control=control))
    await asyncio.sleep(0.05)
    control.cancel()
    summary = await asyncio.wait_for(task, timeout=2)

    store.close()
    assert summary.cancelled
    assert summary.rendered == 0


@pytest.mark.asyncio
async def test_progress_tracks_due_total_and_summary(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    progress = SiteProgress(site_name="example")

    summary = await _run(store, tmp_path, progress=progress)

    store.close()
    assert progress.due_total == 1
    assert progress.render_summary is summary
    assert progress.current_delay == 0


@pytest.mark.asyncio
async def test_retry_renders_failed_record_despite_backoff_and_retry_cap(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    now = datetime.now(UTC)
    seed_record(
        store,
        fetch_status="failed",
        retry_count=MAX_RETRY_COUNT + 1,
        retry_after=now + timedelta(days=1),
        last_attempt_at=now,
    )
    seed_record(
        store,
        source_url="https://example.com/ok",
        canonical_url="https://example.com/ok",
        fetch_status="success",
        last_rendered_at=now,
        last_attempt_at=now,
        extractor_version=EXTRACTOR_VERSION,
    )

    summary = await _run(store, tmp_path, retry=True)

    recovered = store.get("example", "https://example.com/permit")
    store.close()
    assert summary.considered == 1
    assert summary.saved == 1
    assert recovered is not None
    assert recovered.fetch_status == "success"
    assert recovered.retry_count == 0


@pytest.mark.asyncio
async def test_retry_includes_inactive_candidates_only_when_asked(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store, scope_status="inactive_candidate")

    without = await _run(store, tmp_path, retry=True)
    with_inactive = await _run(store, tmp_path, retry=True, include_inactive=True)

    store.close()
    assert without.considered == 0
    assert with_inactive.considered == 1
    assert with_inactive.saved == 1


@pytest.mark.asyncio
async def test_cancel_with_nothing_due_still_reports_cancelled(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    control = JobControl()
    control.cancel()

    summary = await _run(store, tmp_path, control=control)

    store.close()
    assert summary.cancelled
    assert not summary.complete


@pytest.mark.asyncio
async def test_cancel_while_waiting_on_rate_limiter_starts_no_request(tmp_path: Path) -> None:
    store = ManifestStore(path=str(tmp_path / "manifest.db"))
    seed_record(store)
    control = JobControl()
    browser = mock_browser()

    original = HostRateLimiter.wait_for_turn

    async def cancel_during_wait(self: HostRateLimiter) -> None:
        control.cancel()
        await original(self)

    with patch.object(HostRateLimiter, "wait_for_turn", cancel_during_wait):
        summary = await _run(store, tmp_path, browser=browser, control=control)

    store.close()
    assert summary.cancelled
    browser.arun.assert_not_awaited()
