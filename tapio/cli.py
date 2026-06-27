"""Command-line interface for the Tapio Assistant pipeline."""

import logging
from pathlib import Path

import typer
from langchain_chroma import Chroma  # type: ignore[import-not-found]
from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore[import-not-found]
from langchain_text_splitters import MarkdownTextSplitter  # type: ignore[import-not-found]

from tapio.config import ConfigManager
from tapio.config.config_models import RAGConfig
from tapio.config.settings import (
    DEFAULT_CHROMA_COLLECTION,
    DEFAULT_CONTENT_DIR,
    DEFAULT_DIRS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_NUM_RESULTS,
)
from tapio.crawler.runner import CrawlerRunner
from tapio.factories import RAGOrchestratorFactory
from tapio.parser import Parser
from tapio.vectorstore.vectorizer import MarkdownVectorizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress unnecessary warnings
logging.getLogger("onnxruntime").setLevel(logging.ERROR)  # Suppress ONNX warnings
logging.getLogger("transformers").setLevel(
    logging.ERROR,
)  # Suppress potential transformers warnings
logging.getLogger("chromadb").setLevel(logging.WARNING)  # Reduce ChromaDB debug noise


def find_sites_with_crawled_content(content_dir: str, crawled_subdir: str) -> list[str]:
    """Find all sites that have crawled HTML content.

    :param content_dir: The root content directory to search in
    :param crawled_subdir: The subdirectory name containing crawled files
    :return: List of site names that have crawled HTML content
    """
    crawled_sites: list[str] = []
    content_path = Path(content_dir)
    if not content_path.exists():
        return crawled_sites

    for item_path in content_path.iterdir():
        if item_path.is_dir():
            crawled_path = item_path / crawled_subdir
            if crawled_path.is_dir():
                # Check if the crawled directory contains any HTML files
                has_html = any(crawled_path.rglob("*.html"))
                if has_html:
                    crawled_sites.append(item_path.name)

    return crawled_sites


app = typer.Typer(help="Tapio Assistant CLI - Web crawling and parsing tool")


@app.command()
def crawl(
    site: str = typer.Argument(..., help="Site configuration to use for crawling (e.g., 'migri')"),
    depth: int | None = typer.Option(
        None,
        "--depth",
        "-d",
        help="Maximum link-following depth (if not specified, uses config file default)",
    ),
    config_path: str | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to custom parser configurations file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Crawl a website to a configurable depth and save raw HTML content.

    This command takes a site identifier and uses the corresponding configuration
    from the site_configs.yaml file to determine the base URL for crawling.

    The crawler is interruptible - press Ctrl+C to stop and save current progress.

    Example:
        $ python -m tapio.cli crawl migri -d 2
    """
    # Set log level based on verbose flag
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Use ConfigManager for site configuration management
    try:
        config_manager = ConfigManager(config_path)
        available_sites = config_manager.list_available_sites()

        if site not in available_sites:
            typer.echo(f"❌ Unsupported site: {site}")
            typer.echo(f"Available sites: {', '.join(available_sites)}")
            raise typer.Exit(code=1)

        # Get the site configuration
        site_config = config_manager.get_site_config(site)
    except ValueError as e:
        typer.echo(f"❌ Error loading site configuration: {e!s}")
        raise typer.Exit(code=1) from None

    # Get the base URL from the site configuration
    url = site_config.base_url

    # Implement depth precedence logic:
    # 1. Use user-provided value if given
    # 2. Otherwise, use config value (which could be default or explicitly set)
    if depth is not None:
        # User explicitly provided a depth value
        site_config.crawler_config.max_depth = depth

    # Construct the actual output directory path
    crawled_dir = str(Path(DEFAULT_CONTENT_DIR) / site / DEFAULT_DIRS["CRAWLED_DIR"])

    typer.echo(f"🕸️ Starting web crawler for {site} ({url}) with depth {site_config.crawler_config.max_depth}")
    typer.echo(f"💾 Saving HTML content to: {crawled_dir}")
    typer.echo(
        f"⏱️ Using {site_config.crawler_config.delay_between_requests}s delay between requests "
        f"and max {site_config.crawler_config.max_concurrent} concurrent requests",
    )

    try:
        # Initialize crawler runner
        runner = CrawlerRunner()

        typer.echo("⚠️ Press Ctrl+C at any time to interrupt crawling.")

        # Start crawling with simplified interface
        results = runner.run(site, site_config)

        # Output information
        typer.echo(f"✅ Crawling completed! Processed {len(results)} pages.")
        typer.echo(f"💾 Content saved as HTML files in {crawled_dir}")

    except KeyboardInterrupt:
        typer.echo("\n🛑 Crawling interrupted by user")
        typer.echo("✅ Partial results have been saved")
        typer.echo(f"💾 Crawled content saved to {crawled_dir}")
    except Exception as e:
        typer.echo(f"❌ Error during crawling: {e!s}", err=True)
        raise typer.Exit(code=1) from None


def _parse_single_site(config_manager: ConfigManager, site: str, available_sites: list[str]) -> None:
    """Parse a single, named site.

    Args:
        config_manager: Site configuration manager
        site: Name of the site to parse
        available_sites: Names of sites with known configurations
    """
    if site not in available_sites:
        typer.echo(f"❌ Unsupported site: {site}")
        typer.echo(f"Available sites: {', '.join(available_sites)}")
        raise typer.Exit(code=1)

    typer.echo(f"🔧 Using configuration for site: {site}")

    site_config = config_manager.get_site_config(site)
    input_dir = str(Path(DEFAULT_CONTENT_DIR) / site / DEFAULT_DIRS["CRAWLED_DIR"])
    output_dir = str(Path(DEFAULT_CONTENT_DIR) / site / DEFAULT_DIRS["PARSED_DIR"])

    parser = Parser(
        site_name=site,
        site_config=site_config,
        input_dir=input_dir,
        output_dir=output_dir,
    )
    results = parser.parse_all()

    typer.echo(f"✅ Parsing completed! Processed {len(results)} files.")
    parsed_dir = str(Path(DEFAULT_CONTENT_DIR) / site / DEFAULT_DIRS["PARSED_DIR"])
    typer.echo(f"📝 Content saved as Markdown files in {parsed_dir}")
    typer.echo(f"📝 Index created at {parsed_dir}/index.md")


def _parse_all_crawled_sites(config_manager: ConfigManager, available_sites: list[str]) -> None:
    """Parse every site that has crawled content and a matching configuration.

    Args:
        config_manager: Site configuration manager
        available_sites: Names of sites with known configurations
    """
    typer.echo("🔧 No site specified, parsing all available sites with crawled content")

    content_dir = DEFAULT_CONTENT_DIR
    if not Path(content_dir).exists():
        typer.echo(f"❌ Content directory not found: {content_dir}")
        raise typer.Exit(code=1)

    crawled_sites = find_sites_with_crawled_content(content_dir, DEFAULT_DIRS["CRAWLED_DIR"])
    if not crawled_sites:
        typer.echo("❌ No crawled content found to parse")
        raise typer.Exit(code=1)

    typer.echo(f"📂 Found crawled content for sites: {', '.join(crawled_sites)}")

    sites_to_parse = [site_name for site_name in available_sites if site_name in crawled_sites]
    if not sites_to_parse:
        typer.echo("❌ No site configurations found matching crawled content")
        typer.echo(f"Available sites: {', '.join(available_sites)}")
        typer.echo(f"Crawled sites: {', '.join(crawled_sites)}")
        raise typer.Exit(code=1)

    typer.echo(f"🎯 Parsing sites: {', '.join(sites_to_parse)}")

    total_results = []
    for site_name in sites_to_parse:
        typer.echo(f"🔧 Parsing site: {site_name}")
        site_config = config_manager.get_site_config(site_name)
        input_dir = str(Path(DEFAULT_CONTENT_DIR) / site_name / DEFAULT_DIRS["CRAWLED_DIR"])
        output_dir = str(Path(DEFAULT_CONTENT_DIR) / site_name / DEFAULT_DIRS["PARSED_DIR"])

        parser = Parser(
            site_name=site_name,
            site_config=site_config,
            input_dir=input_dir,
            output_dir=output_dir,
        )

        site_results = parser.parse_all()
        total_results.extend(site_results)
        typer.echo(f"  ✅ {site_name}: Processed {len(site_results)} files")

    typer.echo(f"✅ All parsing completed! Processed {len(total_results)} files total.")
    typer.echo(f"📝 Content saved as Markdown files in {DEFAULT_CONTENT_DIR}")
    typer.echo(f"📊 Parsed {len(sites_to_parse)} sites: {', '.join(sites_to_parse)}")


@app.command()
def parse(
    site: str | None = typer.Argument(
        None,
        help="Site to parse (e.g., 'migri'). If not provided, all available sites with crawled content are parsed.",
    ),
    config_path: str | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to custom parser configurations file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Parse HTML files previously crawled and convert to structured Markdown.

    This command reads HTML files from the specified input directory, extracts meaningful content
    based on site-specific configurations, and saves it as Markdown files with YAML frontmatter.

    Configurations define which XPath selectors to use for extracting content and how to convert
    HTML to Markdown for different website types.

    Examples:
        $ python -m tapio.cli parse migri
        $ python -m tapio.cli parse te_palvelut
        $ python -m tapio.cli parse kela --config custom_configs.yaml
    """
    # Set log level based on verbose flag
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    typer.echo(f"📝 Starting HTML parsing from {DEFAULT_DIRS['CRAWLED_DIR']}")
    typer.echo(f"📄 Saving parsed content to: {DEFAULT_DIRS['PARSED_DIR']}")

    try:
        config_manager = ConfigManager(config_path)
        available_sites = config_manager.list_available_sites()

        if site is not None:
            _parse_single_site(config_manager, site, available_sites)
        else:
            _parse_all_crawled_sites(config_manager, available_sites)

    except Exception as e:
        typer.echo(f"❌ Error during parsing: {e!s}", err=True)
        raise typer.Exit(code=1) from None


@app.command()
def vectorize(
    site: str | None = typer.Argument(
        None,
        help="Site to vectorize (e.g. 'migri'). If not provided, all sites are processed.",
    ),
    embedding_model: str = typer.Option(
        "all-MiniLM-L6-v2",
        "--model",
        "-m",
        help="Name of the sentence-transformers model to use",
    ),
    batch_size: int = typer.Option(
        20,
        "--batch-size",
        "-b",
        help="Number of documents to process in each batch",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Vectorize parsed Markdown files and store in a vector database (ChromaDB).

    This command reads parsed Markdown files with frontmatter, generates embeddings,
    and stores them in ChromaDB with associated metadata from the original source.

    Examples:
        $ python -m tapio.cli vectorize migri
        $ python -m tapio.cli vectorize
    """
    # Set log level based on verbose flag
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    db_dir = DEFAULT_DIRS["CHROMA_DIR"]
    collection_name = DEFAULT_CHROMA_COLLECTION

    # Determine input directory based on site parameter
    if site is not None:
        # Process a specific site
        input_dir = str(Path(DEFAULT_CONTENT_DIR) / site / DEFAULT_DIRS["PARSED_DIR"])
        if not Path(input_dir).exists():
            typer.echo(f"❌ No parsed content found for site: {site}")
            typer.echo(f"Expected directory: {input_dir}")
            raise typer.Exit(code=1)
        typer.echo(f"🧠 Starting vectorization of parsed content for site '{site}' from {input_dir}")
    else:
        # Process all sites
        input_dir = DEFAULT_CONTENT_DIR
        typer.echo(f"🧠 Starting vectorization of parsed content from all sites in {input_dir}")

    typer.echo(f"💾 Vector database will be stored in: {db_dir}")
    typer.echo(f"🔤 Using embedding model: {embedding_model}")
    typer.echo(f"📑 Using collection name: {collection_name}")

    try:
        # Create dependencies
        embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
        text_splitter = MarkdownTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
        )
        vector_db = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=db_dir,
        )

        # Initialize vectorizer with injected dependencies
        vectorizer = MarkdownVectorizer(
            vector_db=vector_db,
            text_splitter=text_splitter,
        )

        # Process files in the directory
        typer.echo("⚙️ Processing markdown files...")
        # Process files without site filter (already handled by input_dir)
        count = vectorizer.process_directory(
            input_dir=input_dir,
            site_filter=None,
            batch_size=batch_size,
        )

        # Output information
        typer.echo(f"✅ Vectorization completed! Processed {count} files.")
        typer.echo(f"🔍 Vector database is ready for similarity search in {db_dir}")

    except Exception as e:
        typer.echo(f"❌ Error during vectorization: {e!s}", err=True)
        raise typer.Exit(code=1) from None


@app.command()
def info(
    list_site_configs: bool = typer.Option(
        False,
        "--list-site-configs",
        "-l",
        help="List all available site configurations for parsing",
    ),
    show_site_config: str = typer.Option(
        None,
        "--show-site-config",
        "-s",
        help="Show detailed configuration for a specific site",
    ),
) -> None:
    """Show information about the Tapio Assistant and available commands."""
    # Use ConfigManager directly instead of going through Parser
    config_manager = ConfigManager()

    if list_site_configs:
        # List all available site configurations
        site_configs = config_manager.list_available_sites()
        typer.echo("Available site configurations for parsing:")
        for site_name in site_configs:
            typer.echo(f"  - {site_name}")
        return

    if show_site_config:
        # Show details for a specific site configuration
        try:
            config = config_manager.get_site_config(show_site_config)
            typer.echo(f"Configuration for site: {show_site_config}")
            typer.echo(f"  Base URL: {config.base_url}")
            typer.echo(f"  Base directory: {config.base_dir}")
            typer.echo(f"  Description: {config.description}")
            typer.echo("  Content selectors:")
            for selector in config.parser_config.content_selectors:
                typer.echo(f"    - {selector}")
            typer.echo(f"  Fallback to body: {config.parser_config.fallback_to_body}")
        except ValueError:
            typer.echo(f"Error: Site configuration '{show_site_config}' not found")
        return

    # Show general information
    typer.echo("Tapio Assistant - Web crawling and parsing tool")
    typer.echo("\nAvailable commands:")
    typer.echo("  crawl      - Crawl websites and save HTML content")
    typer.echo("  parse      - Parse HTML files and convert to structured Markdown")
    typer.echo("  vectorize  - Vectorize parsed Markdown files and store in ChromaDB")
    typer.echo("  tapio-app  - Launch the Tapio web interface for querying with the RAG chatbot")
    typer.echo("  info       - Show this information")
    typer.echo("  dev        - Launch the development server for the Tapio Assistant chatbot")
    typer.echo("\nRun a command with --help for more information")


@app.command()
def tapio_app(
    model_name: str = typer.Option(
        "llama3.2:latest",
        "--model-name",
        "-m",
        help="Ollama model to use for LLM inference",
    ),
    max_tokens: int = typer.Option(
        1024,
        "--max-tokens",
        "-t",
        help="Maximum number of tokens to generate",
    ),
    share: bool = typer.Option(
        False,
        "--share",
        help="Create a shareable link for the app",
    ),
) -> None:
    """Launch the Tapio web interface for RAG-powered chatbot."""
    try:
        # Deferred import: avoid loading gradio/torch unless this command actually runs
        from tapio.app import main as launch_app  # noqa: PLC0415

        collection_name = DEFAULT_CHROMA_COLLECTION
        db_dir = DEFAULT_DIRS["CHROMA_DIR"]

        typer.echo(f"🚀 Starting Gradio app with {model_name} model")
        typer.echo(f"📚 Using ChromaDB collection '{collection_name}' from '{db_dir}'")

        if share:
            typer.echo("🔗 Creating a shareable link")

        # Create RAG configuration
        rag_config = RAGConfig(
            collection_name=collection_name,
            persist_directory=db_dir,
            embedding_model_name=DEFAULT_EMBEDDING_MODEL,
            llm_model_name=model_name,
            max_tokens=max_tokens,
            num_results=DEFAULT_NUM_RESULTS,
        )

        # Create RAG orchestrator using factory
        factory = RAGOrchestratorFactory(rag_config)
        orchestrator = factory.create_orchestrator()

        # Launch the Gradio app with orchestrator
        launch_app(
            rag_orchestrator=orchestrator,
            share=share,
        )

    except ImportError as e:
        typer.echo(f"❌ Error importing Gradio: {e!s}", err=True)
        typer.echo("Make sure Gradio is installed with 'uv add gradio'")
        raise typer.Exit(code=1) from None
    except Exception as e:
        typer.echo(f"❌ Error launching Gradio app: {e!s}", err=True)
        raise typer.Exit(code=1) from None


@app.command()
def dev() -> None:
    """Launch the development server for the Tapio Assistant chatbot."""
    typer.echo("🚀 Launching Tapio Assistant chatbot development server...")
    # Call the tapio_app function with default settings
    tapio_app(
        model_name="llama3.2",
        share=False,
    )


@app.command()
def list_sites(
    config_path: str | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to custom parser configurations file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information about each site configuration",
    ),
) -> None:
    """List available site configurations for the parser.

    This command lists all the available sites that can be used with the parse command.
    Use the --verbose flag to see detailed information about each site's configuration.
    """
    try:
        # Use ConfigManager directly for better configuration handling
        config_manager = ConfigManager(config_path)
        available_sites = config_manager.list_available_sites()

        typer.echo("📋 Available Site Configurations:")

        for site_name in available_sites:
            if verbose:
                try:
                    # Get detailed configuration for the site
                    site_config = config_manager.get_site_config(site_name)
                    typer.echo(f"\n📄 {site_name}:")
                    typer.echo(f"  Description: {site_config.description or 'No description'}")
                    typer.echo(f"  Title selector: {site_config.parser_config.title_selector}")
                    typer.echo("  Content selectors:")
                    for selector in site_config.parser_config.content_selectors:
                        typer.echo(f"    - {selector}")
                    typer.echo(f"  Fallback to body: {site_config.parser_config.fallback_to_body}")
                    typer.echo("  Crawler configuration:")
                    typer.echo(f"    - Delay between requests: {site_config.crawler_config.delay_between_requests}s")
                    typer.echo(f"    - Max concurrent requests: {site_config.crawler_config.max_concurrent}")
                except ValueError:
                    # Skip sites with invalid configurations
                    typer.echo(f"\n❌ {site_name}: Invalid configuration")
            else:
                # Simpler output for non-verbose mode
                site_descriptions = config_manager.get_site_descriptions()
                description = f" - {site_descriptions[site_name]}" if site_name in site_descriptions else ""
                typer.echo(f"  • {site_name}{description}")

        typer.echo("\nUse these sites with the parse command, e.g.:")
        typer.echo(f"  $ python -m tapio.cli parse {available_sites[0]}")

    except Exception as e:
        typer.echo(f"❌ Error listing site configurations: {e!s}", err=True)
        raise typer.Exit(code=1) from None


def run_tapio_app() -> None:
    """Entry point for the 'dev' command to launch the Tapio app with default settings."""
    # This function calls the tapio_app command with default settings
    tapio_app(
        model_name="llama3.2",
        share=False,
    )


if __name__ == "__main__":
    app()
