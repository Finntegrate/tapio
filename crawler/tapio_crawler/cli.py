"""CLI for the content-collection service."""

import asyncio

import typer

from tapio_crawler.config import ConfigManager
from tapio_crawler.crawler import CrawlerRunner
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
    typer.echo(
        f"Discovery run {summary.run_id} for {site}: {status}. "
        f"Discovered {summary.discovered}; eligible {summary.eligible}; "
        f"excluded: {excluded}; "
        f"child sitemaps fetched {summary.child_sitemaps_fetched}.",
    )


if __name__ == "__main__":
    app()
