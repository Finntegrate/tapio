"""Tests for the initial, explainable Tapio guide router."""

import pytest

from tapio.agents import AGENTS, AUTO_ROUTE, AgentRouter, get_agent


def test_initial_guide_roster_matches_the_public_product_definition():
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
def test_router_selects_the_guide_for_each_canonical_topic(message, agent_id):
    route = AgentRouter().route(message)

    assert route.agent == get_agent(agent_id)
    assert route.was_explicit is False


def test_selected_guide_takes_precedence_over_automatic_routing():
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
def test_agent_mention_selects_the_named_guide(message, agent_id):
    route = AgentRouter().route(message, AUTO_ROUTE)

    assert route.agent == get_agent(agent_id)
    assert route.was_explicit is True


def test_router_only_treats_standalone_at_mentions_as_guide_selection():
    route = AgentRouter().route("Email sam@Sampo.example.")

    assert route.agent == get_agent("tapio")
    assert route.was_explicit is False


def test_router_keeps_general_questions_with_tapio():
    route = AgentRouter().route("I am moving to Finland and do not know where to begin.")

    assert route.agent == get_agent("tapio")


def test_router_does_not_match_activation_terms_inside_larger_words():
    route = AgentRouter().route("I am reading general information.")

    assert route.agent == get_agent("tapio")
