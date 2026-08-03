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
def crawl(site: str, depth: int | None = typer.Option(None, "--depth", "-d")) -> None:
    """Collect source pages into Markdown for one configured site."""
    config = ConfigManager()
    site_config = config.get_site_config(site)
    if depth is not None:
        site_config.crawler_config.max_depth = depth
    runner = CrawlerRunner()
    results = runner.run(site, site_config)
    summary = runner.last_summary or {}
    status_codes = ", ".join(
        f"{status}={count}"
        for status, count in summary.get("status_codes", {}).items()
    ) or "none"
    typer.echo(
        f"Wrote {len(results)} Markdown documents for {site}. "
        f"Fetched {summary.get('fetched', 0)}; failed {summary.get('failed', 0)}; "
        f"near-empty {summary.get('near_empty', 0)}; "
        f"fallback recoveries {summary.get('fallback_recoveries', 0)}; "
        f"HTTP statuses: {status_codes}."
    )


if __name__ == "__main__":
    app()
