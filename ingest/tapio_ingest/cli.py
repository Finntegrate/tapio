"""CLI for the document-ingestion service."""

import os
from pathlib import Path

import typer
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownTextSplitter

from tapio_ingest.vectorstore.vectorizer import MarkdownVectorizer

app = typer.Typer(help="Ingest crawler Markdown into Tapio's vector collection.")

# An external volume can supply this path; local development uses the
# monorepo's adjacent ``content/`` directory by default.
DEFAULT_CONTENT_DIR = os.environ.get("TAPIO_CONTENT_DIR", "../content")
# An external volume can supply this path; local development uses the
# monorepo's adjacent ``vectorstore/`` directory by default.
DEFAULT_VECTORSTORE_DIR = os.environ.get(
    "TAPIO_VECTORSTORE_DIR",
    str(Path(__file__).resolve().parents[2] / "vectorstore"),
)


@app.command()
def ingest(
    input_dir: str = typer.Argument(
        DEFAULT_CONTENT_DIR,
        help="Shared crawler Markdown directory",
    ),
    collection: str = typer.Option("tapio_knowledge", "--collection"),
    persist_directory: str = typer.Option(
        DEFAULT_VECTORSTORE_DIR,
        "--persist-directory",
    ),
    embedding_model: str = typer.Option("all-MiniLM-L6-v2", "--embedding-model"),
    site: str | None = typer.Option(
        None,
        "--site",
        help="Only ingest one site's parsed Markdown",
    ),
) -> None:
    """Chunk and index shared-folder Markdown while preserving citations.

    :param input_dir: Shared directory containing crawler Markdown.
    :param collection: Chroma collection that receives the document chunks.
    :param persist_directory: Directory where Chroma persists the collection.
    :param embedding_model: Hugging Face embedding model name.
    :param site: Optional site identifier used to restrict ingestion.
    :return: None.

    :example:
        $ uv run tapio-ingest --site migri
    """
    embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
    store = Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )
    vectorizer = MarkdownVectorizer(
        store,
        MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200),
    )
    processed = vectorizer.process_directory(input_dir, site_filter=site)
    typer.echo(f"Ingested {processed} documents.")


if __name__ == "__main__":
    app()
