"""Health check endpoint."""

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from tapio_backend.dependencies import OrchestratorDep
from tapio_backend.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(orchestrator: OrchestratorDep) -> HealthResponse:
    """Report whether the configured Ollama model is reachable and loaded.

    Args:
        orchestrator: Shared RAG orchestrator, injected.

    Returns:
        Whether the configured model is currently available.
    """
    available = await run_in_threadpool(orchestrator.check_model_availability)
    return HealthResponse(model_available=available)
