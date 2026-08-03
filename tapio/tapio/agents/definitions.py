"""Canonical, user-facing definitions for Tapio's initial guide team."""

from dataclasses import dataclass
from typing import Final, Literal

AgentId = Literal["tapio", "ilmarinen", "sampo", "rauni", "otso"]


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Describe a specialist's scope and how it appears to a user.

    Args:
        id: Stable identifier used for routing and prompt selection.
        name: Display name shown to users.
        title: Short, user-facing role title.
        category: Topic area used to explain automatic routing.
        summary: Brief description of the guide's support.
        responsibilities: Topics the guide is equipped to address.
        activation_terms: Terms used to score automatic routing.
        out_of_scope: Support the guide should not provide.
        color: Visual accent name used in the interface.
        specialist_prompt: Optional prompt template that narrows the shared
            Tapio system prompt to this guide's domain.
    """

    id: AgentId
    name: str
    title: str
    category: str
    summary: str
    responsibilities: tuple[str, ...]
    activation_terms: tuple[str, ...]
    out_of_scope: str
    color: str
    specialist_prompt: str | None = None


AGENTS: Final[tuple[AgentDefinition, ...]] = (
    AgentDefinition(
        id="tapio",
        name="Tapio",
        title="Forest guide and coordinator",
        category="Conversation guidance",
        summary="Understands your situation, brings in the right guide, and keeps your next step clear.",
        responsibilities=("clarification", "routing", "cross-guide summaries", "safe handoffs"),
        activation_terms=(),
        out_of_scope="Does not replace official authorities or specialist guidance.",
        color="forest",
    ),
    AgentDefinition(
        id="ilmarinen",
        name="Ilmarinen",
        title="Craftsman of documentation",
        category="Immigration and legal processes",
        summary="Helps you understand residence permits, visas, applications, and official paperwork.",
        responsibilities=("residence permits", "visa processes", "applications", "official documents"),
        activation_terms=(
            "residence permit",
            "work permit",
            "visa",
            "application",
            "apply",
            "document",
            "form",
            "passport",
            "migri",
            "citizenship",
        ),
        out_of_scope="Employment opportunities, benefits, and housing choices without a paperwork question.",
        color="forest",
        specialist_prompt="agents/ilmarinen",
    ),
    AgentDefinition(
        id="sampo",
        name="Sampo",
        title="Prosperity guide",
        category="Economic integration",
        summary="Supports job searching, professional networking, and understanding Finnish workplace culture.",
        responsibilities=("job searching", "professional networking", "workplace culture", "career pathways"),
        activation_terms=(
            "job",
            "career",
            "employment",
            "employer",
            "workplace",
            "networking",
            "cv",
            "resume",
            "interview",
        ),
        out_of_scope="Permit applications and legal employment eligibility questions.",
        color="amber",
        specialist_prompt="agents/sampo",
    ),
    AgentDefinition(
        id="rauni",
        name="Rauni",
        title="Prosperity guardian",
        category="Social services and benefits",
        summary="Helps you navigate Kela, social security, benefits, and family support.",
        responsibilities=("Kela benefits", "social security", "family support", "service eligibility"),
        activation_terms=(
            "kela",
            "benefit",
            "benefits",
            "social security",
            "allowance",
            "family support",
            "parental",
            "unemployment benefit",
        ),
        out_of_scope="Medical diagnosis and legal representation.",
        color="nordic",
        specialist_prompt="agents/rauni",
    ),
    AgentDefinition(
        id="otso",
        name="Otso",
        title="Housing guardian",
        category="Settlement and daily life",
        summary="Helps you understand housing, rental agreements, tenant rights, and settling into daily life.",
        responsibilities=("housing search", "rental agreements", "tenant rights", "housing benefits"),
        activation_terms=(
            "housing",
            "home",
            "apartment",
            "rent",
            "rental",
            "landlord",
            "tenant",
            "lease",
        ),
        out_of_scope="Immigration applications and financial-benefit eligibility beyond housing context.",
        color="nordic",
        specialist_prompt="agents/otso",
    ),
)

AGENTS_BY_ID: Final[dict[AgentId, AgentDefinition]] = {agent.id: agent for agent in AGENTS}


def get_agent(agent_id: str) -> AgentDefinition:
    """Return an agent definition by ID.

    Args:
        agent_id: Stable identifier for a guide in the initial team.

    Returns:
        The matching guide definition.

    Raises:
        ValueError: If ``agent_id`` is not part of the supported initial team.
    """
    try:
        return AGENTS_BY_ID[agent_id]  # type: ignore[index]
    except KeyError as error:
        msg = f"Unknown Tapio agent: {agent_id}"
        raise ValueError(msg) from error
