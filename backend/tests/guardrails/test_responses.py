"""Tests for guardrail interception copy (#29)."""

from unittest.mock import Mock

import pytest

from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.guardrails.resources import CrisisResource, CrisisResourceList
from app.guardrails.responses import _INTRO_TIMEOUT_SECONDS, build_guardrail_response

_DRAFT_RESOURCE_LIST = CrisisResourceList(
    version=1,
    status="draft",
    resources=(
        CrisisResource(
            id="test-crisis-line",
            category="mental_health_crisis",
            name="Test Crisis Line",
            description="A test resource.",
            url="https://example.com/crisis",
            phone="000",
            languages=("en",),
            hours="24/7",
        ),
    ),
)


def _mock_llm_service(intro_text: str = "Localized intro text.") -> Mock:
    service = Mock()
    service.generate_response.return_value = intro_text
    return service


async def test_out_of_scope_response_uses_the_localized_intro_only() -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    llm_service = _mock_llm_service("Tämä ei liity Suomeen asettumiseen.")

    response = await build_guardrail_response(match, "Kirjoita minulle runo.", llm_service)

    assert response == "Tämä ei liity Suomeen asettumiseen."


async def test_crisis_response_appends_matching_resources_after_the_localized_intro() -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis", "emergency"),
    )
    llm_service = _mock_llm_service("This sounds urgent.")

    response = await build_guardrail_response(match, "I want to kill myself.", llm_service)

    assert response.startswith("This sounds urgent.\n\n")
    assert "MIELI Crisis Helpline" in response
    assert "General emergency number (112)" in response
    assert "112" in response
    assert "https://mieli.fi" in response


async def test_legal_sensitive_response_lists_legal_aid_resources() -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.LEGAL_SENSITIVE,
        reason="asylum process",
        resource_categories=("legal_aid", "immigration_authority"),
    )
    llm_service = _mock_llm_service("This is a legal matter.")

    response = await build_guardrail_response(match, "I was denied asylum.", llm_service)

    assert "Oikeusapu" in response
    assert "Finnish Immigration Service (Migri)" in response


async def test_response_falls_back_to_intro_when_no_resources_match() -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("a_category_with_no_entries",),
    )
    llm_service = _mock_llm_service("This sounds urgent.")

    response = await build_guardrail_response(match, "some message", llm_service)

    assert response == "This sounds urgent."


async def test_llm_service_receives_the_original_message_for_language_detection() -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    llm_service = _mock_llm_service()

    await build_guardrail_response(match, "Écris-moi un poème.", llm_service)

    prompt = llm_service.generate_response.call_args.kwargs["prompt"]
    assert "Écris-moi un poème." in prompt


@pytest.mark.parametrize("bad_response", ["", "   ", "Error: Could not generate a response."])
async def test_response_raises_when_localization_call_fails_and_no_resources_exist(bad_response: str) -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    llm_service = _mock_llm_service(bad_response)

    with pytest.raises(RuntimeError):
        await build_guardrail_response(match, "some message", llm_service)


@pytest.mark.parametrize("bad_response", ["", "Error: Could not generate a response."])
async def test_crisis_response_falls_back_to_safe_intro_when_localization_fails(bad_response: str) -> None:
    """A crisis match must still surface its resources even if the intro call itself fails."""
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis", "emergency"),
    )
    llm_service = _mock_llm_service(bad_response)

    response = await build_guardrail_response(match, "I want to kill myself.", llm_service)

    assert response.startswith("Please contact one of these services:\n\n")
    assert "MIELI Crisis Helpline" in response
    assert "General emergency number (112)" in response


async def test_legal_sensitive_response_falls_back_to_safe_intro_when_localization_fails() -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.LEGAL_SENSITIVE,
        reason="asylum process",
        resource_categories=("legal_aid", "immigration_authority"),
    )
    llm_service = _mock_llm_service("Error: Could not generate a response.")

    response = await build_guardrail_response(match, "I was denied asylum.", llm_service)

    assert response.startswith("Please contact one of these services:\n\n")
    assert "Oikeusapu" in response


async def test_localized_intro_passes_the_timeout_to_the_llm_service() -> None:
    """The timeout is enforced by the configured LLMProvider's own client (see its tests), not
    here — this only checks the value actually reaches generate_response's `timeout` kwarg."""
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    llm_service = _mock_llm_service()

    await build_guardrail_response(match, "some message", llm_service)

    assert llm_service.generate_response.call_args.kwargs["timeout"] == _INTRO_TIMEOUT_SECONDS


async def test_crisis_resources_withheld_when_gate_enabled_and_status_not_approved(monkeypatch) -> None:
    """The require_approved_crisis_resources fail-closed path withholds specific contacts."""
    monkeypatch.setenv("TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES", "true")
    monkeypatch.setattr("app.guardrails.responses.load_crisis_resources", lambda: _DRAFT_RESOURCE_LIST)
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis",),
    )
    llm_service = _mock_llm_service("Please contact emergency services.")

    response = await build_guardrail_response(match, "I want to kill myself.", llm_service)

    assert "Test Crisis Line" not in response
    assert "000" not in response
    prompt = llm_service.generate_response.call_args.kwargs["prompt"]
    assert "aren't available right now" in prompt


async def test_crisis_resources_shown_when_gate_enabled_and_status_approved(monkeypatch) -> None:
    """The gate only withholds non-approved lists — an approved list still surfaces contacts."""
    approved_list = CrisisResourceList(version=1, status="approved", resources=_DRAFT_RESOURCE_LIST.resources)
    monkeypatch.setenv("TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES", "true")
    monkeypatch.setattr("app.guardrails.responses.load_crisis_resources", lambda: approved_list)
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis",),
    )
    llm_service = _mock_llm_service("Please contact emergency services.")

    response = await build_guardrail_response(match, "I want to kill myself.", llm_service)

    assert "Test Crisis Line" in response


async def test_crisis_resources_shown_when_gate_disabled_regardless_of_status(monkeypatch) -> None:
    """The default (gate disabled) preserves existing behavior: draft data is still shown."""
    monkeypatch.setenv("TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES", "false")
    monkeypatch.setattr("app.guardrails.responses.load_crisis_resources", lambda: _DRAFT_RESOURCE_LIST)
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis",),
    )
    llm_service = _mock_llm_service("Please contact emergency services.")

    response = await build_guardrail_response(match, "I want to kill myself.", llm_service)

    assert "Test Crisis Line" in response


@pytest.mark.parametrize("bad_response", ["", "Error: Could not generate a response."])
async def test_crisis_response_uses_no_resources_fallback_when_unmatched_and_localization_fails(
    bad_response: str,
) -> None:
    """A crisis match with no matching resource category must not surface a bare generic error."""
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("a_category_with_no_entries",),
    )
    llm_service = _mock_llm_service(bad_response)

    response = await build_guardrail_response(match, "I want to kill myself.", llm_service)

    assert response == "Please contact your local emergency services or a trusted support line directly."


async def test_crisis_response_uses_no_resources_fallback_when_gate_withholds_and_localization_fails(
    monkeypatch,
) -> None:
    """Same fallback applies when the gate, not an unmatched category, is why there are no resources."""
    monkeypatch.setenv("TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES", "true")
    monkeypatch.setattr("app.guardrails.responses.load_crisis_resources", lambda: _DRAFT_RESOURCE_LIST)
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis",),
    )
    llm_service = _mock_llm_service("Error: Could not generate a response.")

    response = await build_guardrail_response(match, "I want to kill myself.", llm_service)

    assert response == "Please contact your local emergency services or a trusted support line directly."


async def test_legal_sensitive_response_uses_no_resources_fallback_when_unmatched_and_localization_fails() -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.LEGAL_SENSITIVE,
        reason="asylum process",
        resource_categories=("a_category_with_no_entries",),
    )
    llm_service = _mock_llm_service("Error: Could not generate a response.")

    response = await build_guardrail_response(match, "I was denied asylum.", llm_service)

    assert response == "Please contact your local emergency services or a trusted support line directly."
