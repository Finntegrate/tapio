"""Tests for concurrent per-site job orchestration."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import HttpUrl

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.crawler.crawler import RenderRunSummary
from tapio_crawler.crawler.job_control import JobControl
from tapio_crawler.crawler.jobs import (
    ResourcePeak,
    SiteJob,
    monitor_resources,
    report_progress,
    run_jobs,
)
from tapio_crawler.discovery.runner import DiscoveryRunSummary
from tapio_crawler.manifest.store import ManifestStore


def _job(name: str) -> SiteJob:
    return SiteJob(site_name=name, site_config=SiteConfig(base_url=HttpUrl(f"https://{name}.example")))


def _factory(tmp_path: Path) -> object:
    return lambda: ManifestStore(tmp_path / "manifest.db")


def _patch_runners(discovery: AsyncMock, render: AsyncMock) -> object:
    return (
        patch("tapio_crawler.crawler.jobs.DiscoveryRunner", return_value=MagicMock(run=discovery)),
        patch("tapio_crawler.crawler.jobs.CrawlerRunner", return_value=MagicMock(run_async=render)),
    )


@pytest.mark.asyncio
async def test_full_mode_runs_discovery_then_render_for_every_site(tmp_path: Path) -> None:
    discovery = AsyncMock(side_effect=lambda name, _cfg, **_k: DiscoveryRunSummary(run_id="d", site_name=name))
    render = AsyncMock(side_effect=lambda name, *_a, **_k: RenderRunSummary(run_id="r", site_name=name))
    jobs = [_job("a"), _job("b")]
    discovery_patch, render_patch = _patch_runners(discovery, render)

    with discovery_patch, render_patch:
        await run_jobs(jobs, max_urls=10, batch_size=5, store_factory=_factory(tmp_path))

    assert [job.progress.phase for job in jobs] == ["done", "done"]
    assert all(job.discovery and job.render for job in jobs)
    assert discovery.await_count == 2
    assert render.await_args.kwargs["retry"] is False


@pytest.mark.asyncio
async def test_retry_mode_skips_discovery(tmp_path: Path) -> None:
    discovery = AsyncMock()
    render = AsyncMock(return_value=RenderRunSummary(run_id="r", site_name="a"))
    job = _job("a")
    discovery_patch, render_patch = _patch_runners(discovery, render)

    with discovery_patch, render_patch:
        await run_jobs(
            [job],
            mode="retry",
            max_urls=10,
            batch_size=5,
            include_inactive=True,
            store_factory=_factory(tmp_path),
        )

    discovery.assert_not_awaited()
    assert render.await_args.kwargs["retry"] is True
    assert render.await_args.kwargs["include_inactive"] is True
    assert job.progress.phase == "done"


@pytest.mark.asyncio
async def test_one_site_failing_does_not_stop_the_others(tmp_path: Path) -> None:
    async def discover(name: str, _cfg: SiteConfig, **_k: object) -> DiscoveryRunSummary:
        if name == "bad":
            message = "boom"
            raise RuntimeError(message)
        return DiscoveryRunSummary(run_id="d", site_name=name)

    render = AsyncMock(side_effect=lambda name, *_a, **_k: RenderRunSummary(run_id="r", site_name=name))
    bad, good = _job("bad"), _job("good")
    discovery_patch, render_patch = _patch_runners(AsyncMock(side_effect=discover), render)

    with discovery_patch, render_patch:
        await run_jobs([bad, good], max_urls=10, batch_size=5, store_factory=_factory(tmp_path))

    assert bad.progress.phase == "failed"
    assert isinstance(bad.error, RuntimeError)
    assert good.progress.phase == "done"


@pytest.mark.asyncio
async def test_max_concurrent_sites_limits_simultaneous_jobs(tmp_path: Path) -> None:
    running = 0
    peak = 0

    async def discover(name: str, _cfg: SiteConfig, **_k: object) -> DiscoveryRunSummary:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return DiscoveryRunSummary(run_id="d", site_name=name)

    render = AsyncMock(side_effect=lambda name, *_a, **_k: RenderRunSummary(run_id="r", site_name=name))
    jobs = [_job(name) for name in "abcd"]
    discovery_patch, render_patch = _patch_runners(AsyncMock(side_effect=discover), render)

    with discovery_patch, render_patch:
        await run_jobs(jobs, max_urls=10, batch_size=5, max_concurrent_sites=2, store_factory=_factory(tmp_path))

    assert peak == 2


@pytest.mark.asyncio
async def test_cancel_during_discovery_stops_the_job_without_rendering(tmp_path: Path) -> None:
    started = asyncio.Event()

    async def discover(name: str, _cfg: SiteConfig, *, control: JobControl) -> DiscoveryRunSummary:
        started.set()
        await control.wait_cancelled()
        return DiscoveryRunSummary(run_id="d", site_name=name, complete=False, cancelled=True)

    render = AsyncMock()
    job = _job("a")
    discovery_patch, render_patch = _patch_runners(AsyncMock(side_effect=discover), render)

    with discovery_patch, render_patch:
        task = asyncio.ensure_future(run_jobs([job], max_urls=10, batch_size=5, store_factory=_factory(tmp_path)))
        await started.wait()
        job.control.cancel()
        await asyncio.wait_for(task, timeout=2)

    assert job.progress.phase == "cancelled"
    render.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_factory_failure_fails_only_that_job(tmp_path: Path) -> None:
    calls = 0

    def factory() -> ManifestStore:
        nonlocal calls
        calls += 1
        if calls == 1:
            message = "cannot open manifest"
            raise OSError(message)
        return ManifestStore(tmp_path / "manifest.db")

    discovery = AsyncMock(side_effect=lambda name, _cfg, **_k: DiscoveryRunSummary(run_id="d", site_name=name))
    render = AsyncMock(side_effect=lambda name, *_a, **_k: RenderRunSummary(run_id="r", site_name=name))
    first, second = _job("a"), _job("b")
    discovery_patch, render_patch = _patch_runners(discovery, render)

    with discovery_patch, render_patch:
        await run_jobs([first, second], max_urls=10, batch_size=5, max_concurrent_sites=1, store_factory=factory)

    assert first.progress.phase == "failed"
    assert second.progress.phase == "done"


@pytest.mark.asyncio
async def test_job_cancelled_before_start_is_not_run(tmp_path: Path) -> None:
    discovery = AsyncMock()
    job = _job("a")
    job.control.cancel()
    discovery_patch, render_patch = _patch_runners(discovery, AsyncMock())

    with discovery_patch, render_patch:
        await run_jobs([job], max_urls=10, batch_size=5, store_factory=_factory(tmp_path))

    assert job.progress.phase == "cancelled"
    discovery.assert_not_awaited()


@pytest.mark.asyncio
async def test_render_cancellation_marks_job_cancelled(tmp_path: Path) -> None:
    discovery = AsyncMock(side_effect=lambda name, _cfg, **_k: DiscoveryRunSummary(run_id="d", site_name=name))
    render = AsyncMock(return_value=RenderRunSummary(run_id="r", site_name="a", cancelled=True, complete=False))
    job = _job("a")
    discovery_patch, render_patch = _patch_runners(discovery, render)

    with discovery_patch, render_patch:
        await run_jobs([job], max_urls=10, batch_size=5, store_factory=_factory(tmp_path))

    assert job.progress.phase == "cancelled"


@pytest.mark.asyncio
async def test_report_progress_emits_lines_for_unfinished_jobs_only() -> None:
    running, finished = _job("a"), _job("b")
    running.progress.phase = "render"
    finished.progress.phase = "done"
    lines: list[str] = []

    task = asyncio.ensure_future(report_progress([running, finished], lines.append, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()

    assert lines
    assert all(line.startswith("[a]") for line in lines)


@pytest.mark.asyncio
async def test_monitor_resources_records_peaks() -> None:
    job = _job("a")
    job.progress.phase = "render"
    peak = ResourcePeak()

    task = asyncio.ensure_future(monitor_resources([job], peak, interval=0.01))
    await asyncio.sleep(0.1)
    task.cancel()

    assert peak.samples > 0
    assert peak.rss_bytes > 0
    assert peak.active_jobs == 1


@pytest.mark.asyncio
async def test_jobs_sharing_a_host_run_one_after_another(tmp_path: Path) -> None:
    running = 0
    peak = 0

    async def discover(name: str, _cfg: SiteConfig, **_k: object) -> DiscoveryRunSummary:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return DiscoveryRunSummary(run_id="d", site_name=name)

    render = AsyncMock(side_effect=lambda name, *_a, **_k: RenderRunSummary(run_id="r", site_name=name))
    same_host = [
        SiteJob(site_name=name, site_config=SiteConfig(base_url=HttpUrl("https://shared.example")))
        for name in ("one", "two")
    ]
    discovery_patch, render_patch = _patch_runners(AsyncMock(side_effect=discover), render)

    with discovery_patch, render_patch:
        await run_jobs(same_host, max_urls=10, batch_size=5, store_factory=_factory(tmp_path))

    assert peak == 1
    assert all(job.progress.phase == "done" for job in same_host)


@pytest.mark.asyncio
async def test_incomplete_render_marks_job_incomplete(tmp_path: Path) -> None:
    discovery = AsyncMock(side_effect=lambda name, _cfg, **_k: DiscoveryRunSummary(run_id="d", site_name=name))
    render = AsyncMock(return_value=RenderRunSummary(run_id="r", site_name="a", complete=False))
    job = _job("a")
    discovery_patch, render_patch = _patch_runners(discovery, render)

    with discovery_patch, render_patch:
        await run_jobs([job], max_urls=10, batch_size=5, store_factory=_factory(tmp_path))

    assert job.progress.phase == "incomplete"


@pytest.mark.asyncio
async def test_incomplete_discovery_marks_job_incomplete_but_still_renders(tmp_path: Path) -> None:
    discovery = AsyncMock(
        side_effect=lambda name, _cfg, **_k: DiscoveryRunSummary(run_id="d", site_name=name, complete=False),
    )
    render = AsyncMock(return_value=RenderRunSummary(run_id="r", site_name="a"))
    job = _job("a")
    discovery_patch, render_patch = _patch_runners(discovery, render)

    with discovery_patch, render_patch:
        await run_jobs([job], max_urls=10, batch_size=5, store_factory=_factory(tmp_path))

    assert job.progress.phase == "incomplete"
    render.assert_awaited_once()


@pytest.mark.asyncio
async def test_monitor_resources_reuses_process_objects_between_samples() -> None:
    job = _job("a")
    peak = ResourcePeak()

    task = asyncio.ensure_future(monitor_resources([job], peak, interval=0.01))
    await asyncio.sleep(0.08)
    task.cancel()

    assert peak.processes
