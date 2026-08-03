"""Tests for the initial, explainable Tapio guide router."""

from tapio.agents import AGENTS, AUTO_ROUTE, AgentRouter, get_agent


def test_initial_guide_roster_matches_the_public_product_definition():
    assert [agent.name for agent in AGENTS] == ["Tapio", "Ilmarinen", "Sampo", "Rauni", "Otso"]


def test_router_selects_documentation_guide_for_work_permits():
    route = AgentRouter().route("How long does my work permit application take?")

    assert route.agent == get_agent("ilmarinen")
    assert route.was_explicit is False


def test_router_selects_employment_guide_for_a_job_search():
    route = AgentRouter().route("Where should I start networking for a job in Helsinki?")

    assert route.agent == get_agent("sampo")


def test_selected_guide_takes_precedence_over_automatic_routing():
    route = AgentRouter().route("I need help with a rental agreement", "rauni")

    assert route.agent == get_agent("rauni")
    assert route.was_explicit is True


def test_agent_mention_selects_the_named_guide():
    route = AgentRouter().route("@Otso, what should I check before I sign a lease?", AUTO_ROUTE)

    assert route.agent == get_agent("otso")
    assert route.was_explicit is True


def test_router_keeps_general_questions_with_tapio():
    route = AgentRouter().route("I am moving to Finland and do not know where to begin.")

    assert route.agent == get_agent("tapio")
