"""CLI for the content-collection service."""

from pathlib import Path

import typer

from tapio_crawler.config import ConfigManager
from tapio_crawler.config.settings import DEFAULT_CONTENT_DIR, DEFAULT_DIRS
from tapio_crawler.crawler import CrawlerRunner
from tapio_crawler.parser import Parser

app = typer.Typer(help="Collect and normalize source content for Tapio.")


@app.command("list-sites")
def list_sites() -> None:
    """List the configured source sites."""
    for site in ConfigManager().list_available_sites():
        typer.echo(site)


@app.command()
def crawl(site: str, depth: int | None = typer.Option(None, "--depth", "-d")) -> None:
    """Collect source pages for one configured site."""
    config = ConfigManager()
    site_config = config.get_site_config(site)
    if depth is not None:
        site_config.crawler_config.max_depth = depth
    results = CrawlerRunner().run(site, site_config)
    typer.echo(f"Collected {len(results)} pages for {site}.")


@app.command()
def parse(site: str) -> None:
    """Convert a site's collected HTML into the Markdown handoff contract."""
    config = ConfigManager()
    site_config = config.get_site_config(site)
    input_dir = Path(DEFAULT_CONTENT_DIR) / site / DEFAULT_DIRS["CRAWLED_DIR"]
    output_dir = Path(DEFAULT_CONTENT_DIR) / site / DEFAULT_DIRS["PARSED_DIR"]
    results = Parser(site, site_config, str(input_dir), str(output_dir)).parse_all()
    typer.echo(f"Wrote {len(results)} Markdown documents for {site}.")


if __name__ == "__main__":
    app()
