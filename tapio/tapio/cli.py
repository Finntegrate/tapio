"""CLI for the user-facing Tapio application service."""

import typer

from tapio.app import main
from tapio.config.config_models import RAGConfig
from tapio.config.settings import DEFAULT_LLM_MODEL, DEFAULT_MAX_TOKENS
from tapio.factories import RAGOrchestratorFactory

app = typer.Typer(help="Run the Tapio chat application.")


@app.callback()
def cli() -> None:
    """Expose application commands without starting the interface itself."""


@app.command(name="serve")
def serve(
    model_name: str = typer.Option(DEFAULT_LLM_MODEL, "--model-name"),
    max_tokens: int = typer.Option(DEFAULT_MAX_TOKENS, "--max-tokens"),
) -> None:
    """Start the chat interface against the vector collection populated by ingest."""
    config = RAGConfig(llm_model_name=model_name, max_tokens=max_tokens)
    main(RAGOrchestratorFactory(config).create_orchestrator())


if __name__ == "__main__":
    app()
