"""Guide roster endpoint."""

from fastapi import APIRouter

from app.agents.definitions import AGENTS
from app.schemas import AgentSummary

router = APIRouter()


@router.get("/agents", response_model=list[AgentSummary])
async def list_agents() -> list[AgentSummary]:
    """Return the user-facing guide roster.

    Returns:
        A summary of every guide in the canonical, user-facing roster.
    """
    return [
        AgentSummary(
            id=agent.id,
            name=agent.name,
            title=agent.title,
            category=agent.category,
            summary=agent.summary,
            color=agent.color,
        )
        for agent in AGENTS
    ]
