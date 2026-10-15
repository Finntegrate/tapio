"""Health check endpoint."""

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.dependencies import OrchestratorDep
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health")
async def health(orchestrator: OrchestratorDep) -> HealthResponse:
    """Report whether each configured model (default, per-guide, guardrail) is available.

    Args:
        orchestrator: Shared RAG orchestrator, injected.

    Returns:
        Overall availability, plus availability per model role.
    """
    statuses = await run_in_threadpool(orchestrator.check_model_statuses)
    return HealthResponse(model_available=all(statuses.values()), models=statuses)
