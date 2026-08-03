"""CLI for the document-ingestion service."""

import typer
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownTextSplitter

from tapio_ingest.vectorstore.vectorizer import MarkdownVectorizer

app = typer.Typer(help="Ingest crawler Markdown into Tapio's vector collection.")


@app.command()
def ingest(
    input_dir: str = typer.Argument(..., help="Crawler Markdown output directory"),
    collection: str = typer.Option("tapio_knowledge", "--collection"),
    persist_directory: str = typer.Option("chroma_db", "--persist-directory"),
    embedding_model: str = typer.Option("all-MiniLM-L6-v2", "--embedding-model"),
) -> None:
    """Chunk and index Markdown while preserving its frontmatter citations."""
    embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
    store = Chroma(collection_name=collection, embedding_function=embeddings, persist_directory=persist_directory)
    vectorizer = MarkdownVectorizer(store, MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200))
    typer.echo(f"Ingested {vectorizer.process_directory(input_dir)} documents.")


if __name__ == "__main__":
    app()
