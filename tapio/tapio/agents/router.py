"""Simple, explainable routing for Tapio's initial multi-agent experience."""

import re
from dataclasses import dataclass
from typing import Final

from tapio.agents.definitions import AGENTS, AgentDefinition, get_agent

AUTO_ROUTE: Final = "auto"


@dataclass(frozen=True, slots=True)
class AgentRoute:
    """Record a routing decision that can be shown to the user."""

    agent: AgentDefinition
    reason: str
    was_explicit: bool = False


class AgentRouter:
    """Select the most relevant guide without hiding the decision from users."""

    def route(self, message: str, preferred_agent_id: str = AUTO_ROUTE) -> AgentRoute:
        """Choose a guide using a manual choice, mention, or domain keywords.

        Args:
            message: User message used for guide mentions and topic matching.
            preferred_agent_id: Explicit guide selection, or ``AUTO_ROUTE`` to infer one.

        Returns:
            The selected guide and a user-visible explanation of the decision.
        """
        if preferred_agent_id != AUTO_ROUTE:
            agent = get_agent(preferred_agent_id)
            return AgentRoute(agent=agent, reason="You selected this guide.", was_explicit=True)

        normalized_message = message.casefold()
        for agent in AGENTS:
            if f"@{agent.id}" in normalized_message or f"@{agent.name.casefold()}" in normalized_message:
                return AgentRoute(agent=agent, reason=f"You mentioned @{agent.name}.", was_explicit=True)

        ranked_agents = [(self._score(agent, normalized_message), agent) for agent in AGENTS if agent.id != "tapio"]
        score, agent = max(ranked_agents, key=lambda candidate: candidate[0])
        if score:
            return AgentRoute(agent=agent, reason=f"This looks like a {agent.category.casefold()} question.")

        return AgentRoute(
            agent=get_agent("tapio"),
            reason="Tapio will clarify the best next step before involving a specialist.",
        )

    @staticmethod
    def _score(agent: AgentDefinition, normalized_message: str) -> int:
        """Weight longer terms so specific phrases win over broad keywords.

        Args:
            agent: Guide whose activation terms are evaluated.
            normalized_message: Case-normalized user message to score.

        Returns:
            Aggregate keyword score for the guide.
        """
        return sum(
            len(re.findall(rf"(?<!\w){re.escape(term)}(?!\w)", normalized_message)) * len(term.split())
            for term in agent.activation_terms
        )
