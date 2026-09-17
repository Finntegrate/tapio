"""Tests for loading the approved crisis/escalation resource list (#29, #133)."""

from app.guardrails.resources import load_crisis_resources


def test_load_crisis_resources_parses_the_real_config_file() -> None:
    """Exercise the real ``crisis_resources.yaml`` so a malformed edit fails CI, not just review."""
    resource_list = load_crisis_resources()

    assert resource_list.version == 1
    assert resource_list.status in {"draft", "approved"}
    assert len(resource_list.resources) > 0

    emergency = next(resource for resource in resource_list.resources if resource.id == "emergency-112")
    assert emergency.category == "emergency"
    assert emergency.phone == "112"
    assert "fi" in emergency.languages


def test_by_categories_filters_and_preserves_file_order() -> None:
    resource_list = load_crisis_resources()

    mental_health = resource_list.by_categories(("mental_health_crisis",))

    assert len(mental_health) == 1
    assert mental_health[0].id == "crisis-line-mieli"


def test_by_categories_returns_empty_tuple_for_no_categories() -> None:
    resource_list = load_crisis_resources()

    assert resource_list.by_categories(()) == ()


def test_by_categories_returns_empty_tuple_for_unknown_category() -> None:
    resource_list = load_crisis_resources()

    assert resource_list.by_categories(("not_a_real_category",)) == ()


def test_load_crisis_resources_is_cached() -> None:
    assert load_crisis_resources() is load_crisis_resources()
