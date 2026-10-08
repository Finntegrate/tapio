"""FastAPI application entrypoint for the Tapio backend."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import BackendSettings
from app.config.config_models import RAGConfig
from app.config.llm_settings import GUARDRAIL_ROLE
from app.factories import RAGOrchestratorFactory
from app.guardrails import LLMGuardrailClassifier
from app.routes import agents, chat, health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the shared orchestrator graph and guardrail classifier once per process lifetime.

    Args:
        app: The FastAPI application being started.

    Yields:
        Control back to FastAPI once startup state is attached to ``app.state``.
    """
    factory = RAGOrchestratorFactory(RAGConfig())
    orchestrator = factory.create_orchestrator()
    app.state.orchestrator = orchestrator
    # The chat route talks to the graph directly (see app.graph, OrchestratorGraphDep);
    # app.state.orchestrator itself is kept for /health and for LLMGuardrailClassifier below.
    app.state.orchestrator_graph = orchestrator.graph
    # Built through the same factory as the orchestrator, so the guardrail's LLM checks run
    # against the configured provider/credentials, not always Ollama (#9), unless
    # TAPIO_LLM_MODEL_OVERRIDES gives the guardrail stage its own model (#139).
    app.state.guardrail_classifier = LLMGuardrailClassifier(factory.create_chat_model(role=GUARDRAIL_ROLE))
    logger.info("Tapio backend started")
    yield


def create_app() -> FastAPI:
    """Construct the FastAPI application with routes and CORS configured.

    Returns:
        The configured, ready-to-serve FastAPI application.
    """
    settings = BackendSettings()
    app = FastAPI(title="Tapio backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(agents.router)
    app.include_router(chat.router)
    return app


app = create_app()


def run() -> None:
    """Run the backend with uvicorn, honoring ``BackendSettings`` host/port."""
    settings = BackendSettings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
