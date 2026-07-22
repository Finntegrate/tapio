"""Command-line interface for the Tapio application.

This module provides a Typer-based CLI for interacting with Tapio's various
components including web crawling, vectorization, and running the assistant.
"""

import logging
from pathlib import Path

import typer

from tapio.config import ConfigManager
from tapio.config.config_models import RAGConfig
from tapio.config.settings import DEFAULT_CONTENT_DIR, DEFAULT_DIRS
from tapio.crawler.runner import CrawlerRunner

logger = logging.getLogger(__name__)

app = typer.Typer(help="Tapio - RAG-powered chatbot for finnish services")


@app.command()
def crawl(
    site: str = typer.Argument(..., help="Site identifier from site config (e.g., 'migri')"),
    depth: int | None = typer.Option(None, "--depth", "-d", help="Override max crawl depth"),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Override max pages to crawl"),
    render: bool | None = typer.Option(
        None, "--render/--no-render", help="Override JavaScript rendering (Cloudflare)",
    ),
    config_path: str | None = typer.Option(None, "--config", "-c", help="Custom site config file"),
) -> None:
    """Crawl a website via the Cloudflare /crawl API."""
    try:
        config_manager = ConfigManager(config_path)
        site_config = config_manager.get_site_config(site)

        if depth is not None:
            site_config.crawler_config.max_depth = depth
        if limit is not None:
            site_config.crawler_config.limit = limit
        if render is not None:
            site_config.crawler_config.render = render

        typer.echo(f"Starting crawl for site '{site}' at {site_config.base_url}")
        typer.echo(
            f"Depth: {site_config.crawler_config.max_depth}, "
            f"Limit: {site_config.crawler_config.limit}, "
            f"Render: {site_config.crawler_config.render}, "
            f"Source: {site_config.crawler_config.source}",
        )

        runner = CrawlerRunner()
        results = runner.run(site, site_config)

        typer.echo(f"Crawl completed. Processed {len(results)} pages.")

        output_dir = Path(DEFAULT_CONTENT_DIR) / site / DEFAULT_DIRS["CRAWLED_DIR"]
        typer.echo(f"Output saved to {output_dir}")

    except ValueError as e:
        typer.echo(f"Configuration error: {e}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Crawl failed: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def vectorize(
    input_dir: str = typer.Option(
        f"./{DEFAULT_CONTENT_DIR}",
        "--input-dir",
        "-i",
        help="Base directory containing markdown files from crawls",
    ),
    site_filter: str | None = typer.Option(
        None,
        "--site",
        "-s",
        help="Only vectorize markdown from this specific site (default: all sites)",
    ),
    chunk_size: int = typer.Option(1000, "--chunk-size", help="Size of chunks in characters"),
    chunk_overlap: int = typer.Option(200, "--chunk-overlap", help="Overlap between chunks in characters"),
    collection_name: str = typer.Option("tapio_docs", "--collection-name", "-n", help="Chroma collection name"),
    persist_directory: str = typer.Option(
        DEFAULT_DIRS["CHROMA_DIR"],
        "--persist-dir",
        "-p",
        help="Vector store persistence directory",
    ),
    embedding_model: str = typer.Option(
        "sentence-transformers/all-MiniLM-L6-v2",
        "--embedding-model",
        "-m",
        help="HuggingFace embedding model name",
    ),
) -> None:
    """Create vector embeddings from Markdown files for semantic search."""
    from tapio.vectorstore import Vectorizer

    try:
        typer.echo(f"Starting vectorization from {input_dir}")
        if site_filter:
            typer.echo(f"Filtering to site: {site_filter}")
        typer.echo(f"Using chunk size: {chunk_size} with overlap: {chunk_overlap}")
        typer.echo(f"Using embedding model: {embedding_model}")

        vectorizer = Vectorizer(
            input_dir=input_dir,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedding_model_name=embedding_model,
            site_filter=site_filter,
        )

        collection_name_result = vectorizer.process()

        typer.echo(f"Vectorization completed. Collection name: {collection_name_result}")
        typer.echo(f"Vector store saved to {persist_directory}")

    except Exception as e:
        typer.echo(f"Vectorization failed: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def tapio_app(
    persist_directory: str = typer.Option(
        DEFAULT_DIRS["CHROMA_DIR"],
        "--persist-dir",
        "-p",
        help="Vector store persistence directory",
    ),
    collection_name: str = typer.Option("tapio_docs", "--collection-name", "-n", help="Chroma collection name"),
    embedding_model: str = typer.Option(
        "sentence-transformers/all-MiniLM-L6-v2",
        "--embedding-model",
        "-m",
        help="HuggingFace embedding model name",
    ),
    llm_model: str = typer.Option("llama3.2", "--llm-model", "-l", help="Ollama model to use for chat"),
    llm_base_url: str = typer.Option(
        "http://localhost:11434",
        "--llm-base-url",
        "-u",
        help="Base URL for the Ollama server",
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind the Gradio interface"),
    port: int = typer.Option(7860, "--port", help="Port to run the Gradio interface"),
    share: bool = typer.Option(False, "--share", help="Enable a public shareable link"),
) -> None:
    """Launch the Tapio Assistant with an interactive Gradio chat interface."""
    from tapio.app import TapioApp

    try:
        typer.echo("Starting Tapio Assistant...")

        rag_config = RAGConfig(
            embedding_model_name=embedding_model,
            llm_model_name=llm_model,
            llm_base_url=llm_base_url,
            persist_directory=persist_directory,
            collection_name=collection_name,
        )

        typer.echo(f"Using embedding model: {rag_config.embedding_model_name}")
        typer.echo(f"Using LLM model: {rag_config.llm_model_name}")
        typer.echo(f"Vector store: {rag_config.persist_directory}")
        typer.echo(f"Collection: {rag_config.collection_name}")

        app_instance = TapioApp(rag_config=rag_config)
        app_instance.launch(share=share, server_name=host, server_port=port)

    except Exception as e:
        typer.echo(f"Failed to start Tapio Assistant: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command(name="list-sites")
def list_sites(
    config_path: str = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a custom site configuration file",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed site information"),
) -> None:
    """List all available site configurations."""
    try:
        config_manager = ConfigManager(config_path)
        available_sites = config_manager.list_available_sites()

        if not available_sites:
            typer.echo("No sites found in configuration file.")
            return

        typer.echo(f"Found {len(available_sites)} site configurations:")
        typer.echo("")

        for site in sorted(available_sites):
            site_config = config_manager.get_site_config(site)
            description = site_config.description or "No description"

            if verbose:
                typer.echo(f"Site: {site}")
                typer.echo(f"  Base URL: {site_config.base_url}")
                typer.echo(f"  Description: {description}")
                cc = site_config.crawler_config
                typer.echo(
                    f"  Crawl: depth={cc.max_depth}, limit={cc.limit}, "
                    f"render={cc.render}, source={cc.source}",
                )
                typer.echo("")
            else:
                typer.echo(f"  {site}: {description}")

    except Exception as e:
        typer.echo(f"Error listing sites: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def info(
    site: str = typer.Argument(..., help="Site identifier"),
    config_path: str = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a custom site configuration file",
    ),
) -> None:
    """Show detailed configuration for a site."""
    try:
        config_manager = ConfigManager(config_path)
        site_config = config_manager.get_site_config(site)

        typer.echo(f"Site: {site}")
        typer.echo(f"Base URL: {site_config.base_url}")
        typer.echo(f"Description: {site_config.description or 'No description'}")
        typer.echo("")
        typer.echo("Crawler Configuration:")
        cc = site_config.crawler_config
        typer.echo(f"  Max depth: {cc.max_depth}")
        typer.echo(f"  Limit: {cc.limit}")
        typer.echo(f"  Render JavaScript: {cc.render}")
        typer.echo(f"  Source: {cc.source}")

    except ValueError as e:
        typer.echo(f"Site not found: {e}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Error getting site info: {e}", err=True)
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    app()