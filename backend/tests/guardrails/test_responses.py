"""Tests for guardrail interception copy (#29)."""

from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.guardrails.responses import build_guardrail_response


def test_out_of_scope_response_has_no_resource_list() -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")

    response = build_guardrail_response(match)

    assert "Finland" in response
    assert "http" not in response


def test_crisis_response_lists_matching_resources_with_contact_details() -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis", "emergency"),
    )

    response = build_guardrail_response(match)

    assert "MIELI Crisis Helpline" in response
    assert "General emergency number (112)" in response
    assert "112" in response
    assert "https://mieli.fi" in response


def test_legal_sensitive_response_lists_legal_aid_resources() -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.LEGAL_SENSITIVE,
        reason="asylum process",
        resource_categories=("legal_aid", "immigration_authority"),
    )

    response = build_guardrail_response(match)

    assert "Oikeusapu" in response
    assert "Finnish Immigration Service (Migri)" in response


def test_response_falls_back_to_intro_when_no_resources_match() -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("a_category_with_no_entries",),
    )

    response = build_guardrail_response(match)

    assert response.strip() != ""
    assert "-" not in response
