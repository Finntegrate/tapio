"""CLI for the content-collection service."""

import typer

from tapio_crawler.config import ConfigManager
from tapio_crawler.crawler import CrawlerRunner

app = typer.Typer(help="Collect and normalize source content for Tapio.")


@app.command("list-sites")
def list_sites() -> None:
    """List the configured source sites."""
    for site in ConfigManager().list_available_sites():
        typer.echo(site)


@app.command()
def crawl(
    site: str,
    depth: int | None = typer.Option(None, "--depth", "-d"),
    force: bool = typer.Option(False, "--force", help="Ignore the re-crawl interval."),
) -> None:
    """Collect source pages into Markdown for one configured site."""
    config = ConfigManager()
    site_config = config.get_site_config(site)
    if depth is not None:
        site_config.crawler_config.max_depth = depth
    runner = CrawlerRunner()
    results = runner.run(site, site_config, force=force)
    summary = runner.last_summary
    if summary is None:
        msg = "Crawler finished without a summary."
        raise RuntimeError(msg)
    if summary.get("skipped"):
        typer.echo(
            f"Skipped {site}; it was crawled within its "
            f"{site_config.crawler_config.recrawl_interval_hours}-hour interval. "
            "Use --force to crawl it now.",
        )
        return
    status_codes = (
        ", ".join(
            f"{status}={count}"
            for status, count in summary.get("status_codes", {}).items()
        )
        or "none"
    )
    cache_statuses = (
        ", ".join(
            f"{status}={count}"
            for status, count in summary.get("cache_statuses", {}).items()
        )
        or "none"
    )
    typer.echo(
        f"Wrote {len(results)} Markdown documents for {site}. "
        f"Fetched {summary.get('fetched', 0)}; failed {summary.get('failed', 0)}; "
        f"near-empty {summary.get('near_empty', 0)}; "
        f"fallback recoveries {summary.get('fallback_recoveries', 0)}; "
        f"HTTP statuses: {status_codes}; cache: {cache_statuses}.",
    )


if __name__ == "__main__":
    app()
