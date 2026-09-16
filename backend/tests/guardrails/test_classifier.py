"""Tests for the guardrail input classifier (#29)."""

import pytest

from app.guardrails import GuardrailCategory, GuardrailClassifier


@pytest.mark.parametrize(
    ("message", "resource_categories"),
    [
        ("I want to kill myself and don't know who to talk to.", ("mental_health_crisis", "emergency")),
        ("My partner hits me and I don't know what to do.", ("domestic_abuse_support", "emergency")),
        ("I was sexually assaulted last week, what should I do?", ("crime_victim_support", "emergency")),
        ("This is a medical emergency, please help.", ("emergency",)),
    ],
)
def test_classifier_flags_crisis_messages(message: str, resource_categories: tuple[str, ...]) -> None:
    match = GuardrailClassifier().classify(message)

    assert match is not None
    assert match.category is GuardrailCategory.CRISIS
    assert match.resource_categories == resource_categories


@pytest.mark.parametrize(
    "message",
    [
        "I applied for asylum and got a negative decision, what can I do?",
        "I'm worried about being deported next month.",
        "Migri put me in a detention centre, who can help?",
    ],
)
def test_classifier_flags_legally_sensitive_messages(message: str) -> None:
    match = GuardrailClassifier().classify(message)

    assert match is not None
    assert match.category is GuardrailCategory.LEGAL_SENSITIVE
    assert match.resource_categories == ("legal_aid", "immigration_authority")


@pytest.mark.parametrize(
    "message",
    [
        "Can you write me a poem about autumn?",
        "Give me a recipe for pancakes.",
        "Write me code to sort a list in Python.",
    ],
)
def test_classifier_flags_out_of_scope_messages(message: str) -> None:
    match = GuardrailClassifier().classify(message)

    assert match is not None
    assert match.category is GuardrailCategory.OUT_OF_SCOPE
    assert match.resource_categories == ()


@pytest.mark.parametrize(
    "message",
    [
        "How long does my residence permit application take?",
        "Where should I start networking for a job in Helsinki?",
        "What should I check in a rental agreement?",
        "How do I apply for Kela benefits?",
    ],
)
def test_classifier_does_not_flag_ordinary_immigration_questions(message: str) -> None:
    assert GuardrailClassifier().classify(message) is None


def test_classifier_prefers_crisis_over_other_categories_in_a_mixed_message() -> None:
    message = "I applied for asylum and now I want to kill myself, what do I do?"

    match = GuardrailClassifier().classify(message)

    assert match is not None
    assert match.category is GuardrailCategory.CRISIS


def test_classifier_requires_a_trigger_term_to_be_a_standalone_word() -> None:
    """A trigger term must appear as its own word, not merely as a substring of a longer one."""
    assert GuardrailClassifier().classify("I've been having suicidal thoughts lately.") is not None
    assert GuardrailClassifier().classify("I found suicideprevention.fi while researching for a report.") is None
