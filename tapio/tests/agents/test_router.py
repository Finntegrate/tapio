"""Tests for the initial, explainable Tapio guide router."""

import pytest

from tapio.agents import AGENTS, AUTO_ROUTE, AgentRouter, get_agent


def test_initial_guide_roster_matches_the_public_product_definition() -> None:
    """Keep the canonical roster and prompt references stable."""
    assert [agent.name for agent in AGENTS] == ["Tapio", "Ilmarinen", "Sampo", "Rauni", "Otso"]
    assert get_agent("tapio").specialist_prompt is None
    assert get_agent("sampo").specialist_prompt == "agents/sampo"


@pytest.mark.parametrize(
    ("message", "agent_id"),
    [
        ("How long does my work permit application take?", "ilmarinen"),
        ("Where should I start networking for a job in Helsinki?", "sampo"),
        ("How do I apply for Kela benefits?", "rauni"),
        ("What should I check in a rental agreement?", "otso"),
    ],
)
def test_router_selects_the_guide_for_each_canonical_topic(message: str, agent_id: str) -> None:
    """Route each canonical topic to its specialist."""
    route = AgentRouter().route(message)

    assert route.agent == get_agent(agent_id)
    assert route.was_explicit is False


def test_selected_guide_takes_precedence_over_automatic_routing() -> None:
    """Prefer an explicit guide choice to keyword routing."""
    route = AgentRouter().route("I need help with a rental agreement", "rauni")

    assert route.agent == get_agent("rauni")
    assert route.was_explicit is True


@pytest.mark.parametrize(
    ("message", "agent_id"),
    [
        ("@Tapio, where should I start?", "tapio"),
        ("@Ilmarinen, what documents do I need?", "ilmarinen"),
        ("@Sampo, can you help with my residence permit?", "sampo"),
        ("@Rauni, can you help with a rental agreement?", "rauni"),
        ("@Otso, what should I check before I sign a lease?", "otso"),
    ],
)
def test_agent_mention_selects_the_named_guide(message: str, agent_id: str) -> None:
    """Route direct guide mentions regardless of topic keywords."""
    route = AgentRouter().route(message, AUTO_ROUTE)

    assert route.agent == get_agent(agent_id)
    assert route.was_explicit is True


def test_router_only_treats_standalone_at_mentions_as_guide_selection() -> None:
    """Avoid treating addresses and embedded text as guide mentions."""
    route = AgentRouter().route("Email sam@Sampo.example.")

    assert route.agent == get_agent("tapio")
    assert route.was_explicit is False


def test_router_keeps_general_questions_with_tapio() -> None:
    """Keep broad questions with Tapio until a specialist is needed."""
    route = AgentRouter().route("I am moving to Finland and do not know where to begin.")

    assert route.agent == get_agent("tapio")


def test_router_does_not_match_activation_terms_inside_larger_words() -> None:
    """Require activation terms to be standalone words or phrases."""
    route = AgentRouter().route("I am reading general information.")

    assert route.agent == get_agent("tapio")
