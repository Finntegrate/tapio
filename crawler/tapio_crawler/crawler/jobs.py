"""Concurrent, independently controllable per-site crawl jobs.

Each site runs as its own job with its own ``ManifestStore`` connection (the
manifest uses WAL mode and a busy timeout, so writers for different sites
share one database file safely), its own politeness settings, and its own
``JobControl``. Per-host rate limits are enforced per site by the renderer, so
running sites concurrently does not make any one host see more traffic.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

import psutil

from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.crawler.crawler import RenderRunSummary
from tapio_crawler.crawler.job_control import JobControl, SiteProgress
from tapio_crawler.crawler.runner import CrawlerRunner
from tapio_crawler.discovery.runner import DiscoveryRunner, DiscoveryRunSummary
from tapio_crawler.manifest.store import ManifestStore

logger = logging.getLogger(__name__)

JobMode = Literal["full", "retry"]


@dataclass
class SiteJob:
    """One site's job: its controls, live progress, and eventual results.

    Attributes:
        site_name: Name of the configured source site.
        site_config: That site's configuration.
        control: Pause/cancel control for this job.
        progress: Live progress for this job.
        discovery: Discovery summary, once discovery has finished.
        render: Render summary, once rendering has finished.
        error: The exception that failed the job, if any.
    """

    site_name: str
    site_config: SiteConfig
    control: JobControl = field(default_factory=JobControl)
    progress: SiteProgress = field(init=False)
    discovery: DiscoveryRunSummary | None = None
    render: RenderRunSummary | None = None
    error: Exception | None = None

    def __post_init__(self) -> None:
        """Bind the progress object to this job's site."""
        self.progress = SiteProgress(site_name=self.site_name)


@dataclass
class ResourcePeak:
    """Highest resource use sampled across the process tree while jobs ran.

    Attributes:
        rss_bytes: Peak resident memory of this process plus all children
            (the browsers Crawl4AI launches).
        cpu_percent: Peak CPU use of the whole tree, where 100 is one core.
        active_jobs: Most jobs that were rendering/discovering at once.
        samples: Number of samples taken.
    """

    rss_bytes: int = 0
    cpu_percent: float = 0.0
    active_jobs: int = 0
    samples: int = 0


def _sample_tree(root: psutil.Process) -> tuple[int, float]:
    """Return total RSS and CPU percent for ``root`` and its descendants."""
    rss = 0
    cpu = 0.0
    for process in [root, *root.children(recursive=True)]:
        try:
            rss += process.memory_info().rss
            cpu += process.cpu_percent(interval=None)
        except psutil.NoSuchProcess, psutil.AccessDenied:
            continue
    return rss, cpu


def sample_resources(jobs: Iterable[SiteJob], peak: ResourcePeak) -> None:
    """Take one sample of the process tree and fold it into ``peak``."""
    rss, cpu = _sample_tree(psutil.Process(os.getpid()))
    active = sum(1 for job in jobs if job.progress.phase in ("discovery", "render"))
    peak.rss_bytes = max(peak.rss_bytes, rss)
    peak.cpu_percent = max(peak.cpu_percent, cpu)
    peak.active_jobs = max(peak.active_jobs, active)
    peak.samples += 1


async def monitor_resources(
    jobs: Iterable[SiteJob],
    peak: ResourcePeak,
    *,
    interval: float = 2.0,
) -> None:
    """Sample the process tree until cancelled, recording peaks in ``peak``.

    This is how to measure what concurrent site jobs cost: run with
    ``--max-concurrent-sites`` set to 1, 2, ... and compare the reported peaks.
    """
    job_list = list(jobs)
    _sample_tree(psutil.Process(os.getpid()))  # prime cpu_percent, whose first reading is always 0
    while True:
        await asyncio.sleep(interval)
        sample_resources(job_list, peak)


async def report_progress(
    jobs: Iterable[SiteJob],
    emit: Callable[[str], None],
    *,
    interval: float = 10.0,
) -> None:
    """Emit one progress line per unfinished job every ``interval`` seconds."""
    job_list = list(jobs)
    while True:
        await asyncio.sleep(interval)
        for job in job_list:
            if job.progress.phase not in ("done", "cancelled", "failed"):
                emit(job.progress.describe(paused=job.control.paused))


async def _run_discovery(job: SiteJob, store: ManifestStore) -> bool:
    """Run discovery to completion or cooperative cancel; return whether it finished.

    Pause and cancel are enforced inside discovery, before each request, so a
    cancel lets the request in flight finish rather than aborting it.
    """
    job.discovery = await DiscoveryRunner(store).run(job.site_name, job.site_config, control=job.control)
    return not job.discovery.cancelled


async def _run_job(  # noqa: PLR0913
    job: SiteJob,
    *,
    mode: JobMode,
    max_urls: int,
    batch_size: int,
    force: bool,
    include_inactive: bool,
    store_factory: Callable[[], ManifestStore],
) -> None:
    """Run one site's discovery (full mode) and render phases to completion."""
    if job.control.cancelled:
        job.progress.phase = "cancelled"
        return
    store: ManifestStore | None = None
    try:
        store = store_factory()
        if mode == "full":
            job.progress.phase = "discovery"
            if not await _run_discovery(job, store):
                job.progress.phase = "cancelled"
                return
            if not await job.control.checkpoint():
                job.progress.phase = "cancelled"
                return
        job.progress.phase = "render"
        job.render = await CrawlerRunner(store).run_async(
            job.site_name,
            job.site_config,
            max_urls=max_urls,
            batch_size=batch_size,
            force=force,
            retry=mode == "retry",
            include_inactive=include_inactive,
            control=job.control,
            progress=job.progress,
        )
        job.progress.phase = "cancelled" if job.render.cancelled else "done"
    except Exception as error:
        logger.exception("Job for %s failed", job.site_name)
        job.error = error
        job.progress.phase = "failed"
    finally:
        if store is not None:
            store.close()


async def run_jobs(  # noqa: PLR0913
    jobs: list[SiteJob],
    *,
    mode: JobMode = "full",
    max_urls: int,
    batch_size: int,
    force: bool = False,
    include_inactive: bool = False,
    max_concurrent_sites: int | None = None,
    store_factory: Callable[[], ManifestStore] = ManifestStore,
) -> None:
    """Run ``jobs`` concurrently, at most ``max_concurrent_sites`` at a time.

    Args:
        jobs: The site jobs to run; results are written back onto each job.
        mode: ``"full"`` runs discovery then render; ``"retry"`` re-renders
            failed records only, with no discovery.
        max_urls: Per-site hard cap on records rendered.
        batch_size: Manifest page size used while selecting records.
        force: Ignore refresh schedules (full mode only).
        include_inactive: In retry mode, also retry ``inactive_candidate`` records.
        max_concurrent_sites: Cap on simultaneously running sites; ``None``
            runs every job at once.
        store_factory: Opens one manifest connection per job.
    """
    limit = asyncio.Semaphore(max_concurrent_sites or max(1, len(jobs)))

    async def gated(job: SiteJob) -> None:
        async with limit:
            await _run_job(
                job,
                mode=mode,
                max_urls=max_urls,
                batch_size=batch_size,
                force=force,
                include_inactive=include_inactive,
                store_factory=store_factory,
            )

    await asyncio.gather(*(gated(job) for job in jobs))
