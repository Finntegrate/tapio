"""CLI for the content-collection service."""

import asyncio
import contextlib
import signal

import typer

from tapio_crawler.config import ConfigManager
from tapio_crawler.crawler import CrawlerRunner
from tapio_crawler.crawler.jobs import (
    JobMode,
    ResourcePeak,
    SiteJob,
    monitor_resources,
    report_progress,
    run_jobs,
)
from tapio_crawler.discovery.runner import DiscoveryRunner, MisconfiguredDiscoveryError
from tapio_crawler.manifest.store import ManifestStore

app = typer.Typer(help="Collect and normalize source content for Tapio.")


@app.command("list-sites")
def list_sites() -> None:
    """List the configured source sites."""
    for site in ConfigManager().list_available_sites():
        typer.echo(site)


@app.command()
def crawl(
    site: str,
    max_urls: int = typer.Option(
        5_000,
        "--max-urls",
        help="Hard cap on manifest records rendered this run.",
    ),
    batch_size: int = typer.Option(
        500,
        "--batch-size",
        help="Manifest page size used while selecting due records.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Ignore each record's refresh schedule and render every eligible record.",
    ),
) -> None:
    """Render due manifest records into Markdown for one configured site.

    Run ``discover <site>`` first to populate the manifest this command reads
    from.
    """
    config = ConfigManager()
    site_config = config.get_site_config(site)
    store = ManifestStore()
    try:
        runner = CrawlerRunner(store)
        summary = runner.run(site, site_config, max_urls=max_urls, batch_size=batch_size, force=force)
    finally:
        store.close()

    status = "complete" if summary.complete else "incomplete"
    status_codes = ", ".join(f"{code}={count}" for code, count in summary.status_codes.items()) or "none"
    cache_statuses = ", ".join(f"{status_}={count}" for status_, count in summary.cache_statuses.items()) or "none"
    typer.echo(
        f"Render run {summary.run_id} for {site}: {status}. "
        f"Considered {summary.considered}; rendered {summary.rendered}; saved {summary.saved}; "
        f"low-quality {summary.low_quality}; failed {summary.failed}; retried {summary.retried}; "
        f"coverage {summary.coverage_percent:.1f}% ({summary.current_total}/{summary.eligible_total}). "
        f"HTTP statuses: {status_codes}; cache: {cache_statuses}.",
    )
    coverage_target = site_config.crawler_config.refresh.coverage_target_percent
    if summary.coverage_percent < coverage_target:
        typer.echo(
            f"WARNING: coverage {summary.coverage_percent:.1f}% is below the "
            f"{coverage_target:.1f}% target configured for {site}.",
        )


@app.command()
def discover(site: str) -> None:
    """Discover a site's URL inventory and record it in the manifest.

    Args:
        site: Name of the configured source site to discover.

    Raises:
        typer.Exit: With code 1 if the site has no configured way to
            discover URLs (see ``MisconfiguredDiscoveryError``).
    """
    config = ConfigManager()
    site_config = config.get_site_config(site)
    store = ManifestStore()
    try:
        runner = DiscoveryRunner(store)
        try:
            summary = asyncio.run(runner.run(site, site_config))
        except MisconfiguredDiscoveryError as error:
            typer.echo(str(error))
            raise typer.Exit(code=1) from error
    finally:
        store.close()

    excluded = ", ".join(f"{reason}={count}" for reason, count in summary.excluded_by_reason.items()) or "none"
    status = "complete" if summary.complete else "incomplete"
    cache_note = " (cache hit; no HTTP requests made)" if summary.cached else ""
    sitemap_urls = ", ".join(summary.sitemap_urls) or "none"
    typer.echo(
        f"Discovery run {summary.run_id} for {site}: {status}{cache_note}. "
        f"Discovered {summary.discovered}; eligible {summary.eligible}; "
        f"excluded: {excluded}; "
        f"child sitemaps fetched {summary.child_sitemaps_fetched}. "
        f"robots.txt: {summary.robots_txt_url or 'none'}; sitemaps: {sitemap_urls}.",
    )


def _install_signal_controls(jobs: list[SiteJob]) -> None:
    """Map signals onto every job's controls for the life of the running loop.

    ``SIGINT``/``SIGTERM`` request a graceful cancel (a second ``SIGINT``
    falls back to an immediate ``KeyboardInterrupt``); ``SIGUSR1`` pauses and
    ``SIGUSR2`` resumes. Platforms without loop signal support (Windows) just
    keep Python's default interrupt behaviour.
    """
    loop = asyncio.get_running_loop()

    def cancel_all() -> None:
        typer.echo("Cancelling: finishing in-flight requests, then stopping. Press Ctrl-C again to force quit.")
        for job in jobs:
            job.control.cancel()
        with contextlib.suppress(NotImplementedError, ValueError):
            loop.remove_signal_handler(signal.SIGINT)

    def pause_all() -> None:
        typer.echo("Pausing: no new requests will start. Send SIGUSR2 to resume.")
        for job in jobs:
            job.control.pause()

    def resume_all() -> None:
        typer.echo("Resuming.")
        for job in jobs:
            job.control.resume()

    handlers = [
        (signal.SIGINT, cancel_all),
        (signal.SIGTERM, cancel_all),
        (getattr(signal, "SIGUSR1", None), pause_all),
        (getattr(signal, "SIGUSR2", None), resume_all),
    ]
    for sig, handler in handlers:
        if sig is None:
            continue
        with contextlib.suppress(NotImplementedError, ValueError):
            loop.add_signal_handler(sig, handler)


def _resolve_jobs(config: ConfigManager, sites: list[str] | None) -> list[SiteJob]:
    """Build one job per requested site, or per configured site when none given."""
    names = list(sites) if sites else config.list_available_sites()
    if not names:
        typer.echo("No crawler sites are configured.")
        raise typer.Exit(code=1)
    return [SiteJob(site_name=name, site_config=config.get_site_config(name)) for name in names]


def _run_site_jobs(  # noqa: PLR0913
    sites: list[str] | None,
    *,
    mode: JobMode,
    max_urls: int,
    batch_size: int,
    force: bool,
    include_inactive: bool,
    max_concurrent_sites: int | None,
    progress_interval: float,
    report_resources: bool,
) -> None:
    """Run site jobs concurrently with signal controls, progress, and a final report."""
    jobs = _resolve_jobs(ConfigManager(), sites)
    peak = ResourcePeak()

    async def main() -> None:
        _install_signal_controls(jobs)
        helpers = [asyncio.create_task(report_progress(jobs, typer.echo, interval=progress_interval))]
        if report_resources:
            helpers.append(asyncio.create_task(monitor_resources(jobs, peak)))
        try:
            await run_jobs(
                jobs,
                mode=mode,
                max_urls=max_urls,
                batch_size=batch_size,
                force=force,
                include_inactive=include_inactive,
                max_concurrent_sites=max_concurrent_sites,
            )
        finally:
            for helper in helpers:
                helper.cancel()

    asyncio.run(main())

    for job in jobs:
        typer.echo(_describe_result(job))
    if report_resources:
        typer.echo(
            f"Resources: peak {peak.rss_bytes / 1024**2:.0f} MiB RSS and {peak.cpu_percent:.0f}% CPU "
            f"(100% = one core) across the process tree, with up to {peak.active_jobs} site job(s) active "
            f"({peak.samples} samples).",
        )
    if any(job.error is not None for job in jobs):
        raise typer.Exit(code=1)
    if any(job.progress.phase == "cancelled" for job in jobs):
        raise typer.Exit(code=130)


def _describe_result(job: SiteJob) -> str:
    """Return the final one-line result for a finished job."""
    if job.error is not None:
        return f"[{job.site_name}] FAILED: {job.error}"
    parts = [f"[{job.site_name}] {job.progress.phase}"]
    if job.discovery is not None:
        parts.append(f"discovered {job.discovery.discovered}; eligible {job.discovery.eligible}")
    if job.render is not None:
        render = job.render
        parts.append(
            f"considered {render.considered}; rendered {render.rendered}; saved {render.saved}; "
            f"failed {render.failed}; retried {render.retried}; "
            f"coverage {render.coverage_percent:.1f}% ({render.current_total}/{render.eligible_total})",
        )
    return " | ".join(parts)


_SITES_ARGUMENT = typer.Argument(None, help="Sites to run. Defaults to every configured site.")
_MAX_URLS_OPTION = typer.Option(5_000, "--max-urls", help="Hard cap on manifest records rendered per site.")
_BATCH_SIZE_OPTION = typer.Option(500, "--batch-size", help="Manifest page size used while selecting records.")
_MAX_CONCURRENT_SITES_OPTION = typer.Option(
    None,
    "--max-concurrent-sites",
    min=1,
    help="Run at most this many sites at once. Defaults to all selected sites; lower it on constrained hosts.",
)
_PROGRESS_INTERVAL_OPTION = typer.Option(10.0, "--progress-interval", help="Seconds between progress lines.")
_REPORT_RESOURCES_OPTION = typer.Option(
    False,
    "--report-resources",
    help="Sample memory/CPU of this process and its browsers, and report the peak.",
)


@app.command("run-all")
def run_all(  # noqa: PLR0913, PLR0917
    sites: list[str] | None = _SITES_ARGUMENT,
    max_urls: int = _MAX_URLS_OPTION,
    batch_size: int = _BATCH_SIZE_OPTION,
    max_concurrent_sites: int | None = _MAX_CONCURRENT_SITES_OPTION,
    progress_interval: float = _PROGRESS_INTERVAL_OPTION,
    report_resources: bool = _REPORT_RESOURCES_OPTION,
    force: bool = typer.Option(False, "--force", help="Ignore refresh schedules and render every eligible record."),
) -> None:
    """Discover then render several sites as independent concurrent jobs.

    Each site keeps its own politeness settings. While running, SIGINT/SIGTERM
    cancel gracefully (in-flight requests finish, the manifest stays resumable),
    SIGUSR1 pauses, and SIGUSR2 resumes.
    """
    _run_site_jobs(
        sites,
        mode="full",
        max_urls=max_urls,
        batch_size=batch_size,
        force=force,
        include_inactive=False,
        max_concurrent_sites=max_concurrent_sites,
        progress_interval=progress_interval,
        report_resources=report_resources,
    )


@app.command()
def retry(  # noqa: PLR0913, PLR0917
    sites: list[str] | None = _SITES_ARGUMENT,
    max_urls: int = _MAX_URLS_OPTION,
    batch_size: int = _BATCH_SIZE_OPTION,
    max_concurrent_sites: int | None = _MAX_CONCURRENT_SITES_OPTION,
    progress_interval: float = _PROGRESS_INTERVAL_OPTION,
    report_resources: bool = _REPORT_RESOURCES_OPTION,
    include_inactive: bool = typer.Option(
        False,
        "--include-inactive",
        help="Also re-render inactive_candidate records.",
    ),
) -> None:
    """Re-render failed records without a full discover + crawl cycle.

    Ignores retry backoff and the per-URL retry cap, since an operator is
    asking for the attempt now. Supports the same pause/cancel signals as
    ``run-all``.
    """
    _run_site_jobs(
        sites,
        mode="retry",
        max_urls=max_urls,
        batch_size=batch_size,
        force=False,
        include_inactive=include_inactive,
        max_concurrent_sites=max_concurrent_sites,
        progress_interval=progress_interval,
        report_resources=report_resources,
    )


if __name__ == "__main__":
    app()
