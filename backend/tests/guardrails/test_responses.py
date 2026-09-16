"""Tests for guardrail interception copy (#29)."""

from unittest.mock import Mock

import pytest

from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.guardrails.responses import build_guardrail_response


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
async def test_response_raises_when_localization_call_fails(bad_response: str) -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    llm_service = _mock_llm_service(bad_response)

    with pytest.raises(RuntimeError):
        await build_guardrail_response(match, "some message", llm_service)
