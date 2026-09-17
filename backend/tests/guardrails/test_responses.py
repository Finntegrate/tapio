"""Tests for guardrail interception copy (#29)."""

from unittest.mock import Mock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

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


def _patch_chat_model(
    monkeypatch: pytest.MonkeyPatch,
    intro_text: str | None = "Localized intro text.",
    *,
    raises: bool = False,
) -> Mock:
    """Patch the model ``_localized_intro`` builds for itself, and return it for assertions.

    ``build_guardrail_response`` builds its own short-timeout model per call (see
    ``app.guardrails.responses._localized_intro``) rather than taking an injected one, so
    tests control its behavior by patching the factory function it calls.
    """
    model = Mock(spec=BaseChatModel)
    if raises:
        model.invoke.side_effect = RuntimeError("The model call failed.")
    else:
        model.invoke.return_value = AIMessage(content=intro_text)
    monkeypatch.setattr("app.guardrails.responses.build_chat_model", lambda *_args, **_kwargs: model)
    return model


def _sent_prompt(model: Mock) -> str:
    """Extract the prompt text ``_localized_intro`` passed to ``model.invoke``."""
    messages = model.invoke.call_args.args[0]
    return messages[-1]["content"]


async def test_out_of_scope_response_uses_the_localized_intro_only(monkeypatch: pytest.MonkeyPatch) -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    _patch_chat_model(monkeypatch, "Tämä ei liity Suomeen asettumiseen.")

    response = await build_guardrail_response(match, "Kirjoita minulle runo.")

    assert response == "Tämä ei liity Suomeen asettumiseen."


async def test_crisis_response_appends_matching_resources_after_the_localized_intro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis", "emergency"),
    )
    _patch_chat_model(monkeypatch, "This sounds urgent.")

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert response.startswith("This sounds urgent.\n\n")
    assert "MIELI Crisis Helpline" in response
    assert "General emergency number (112)" in response
    assert "112" in response
    assert "https://mieli.fi" in response


async def test_legal_sensitive_response_lists_legal_aid_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.LEGAL_SENSITIVE,
        reason="asylum process",
        resource_categories=("legal_aid", "immigration_authority"),
    )
    _patch_chat_model(monkeypatch, "This is a legal matter.")

    response = await build_guardrail_response(match, "I was denied asylum.")

    assert "Oikeusapu" in response
    assert "Finnish Immigration Service (Migri)" in response


async def test_response_falls_back_to_intro_when_no_resources_match(monkeypatch: pytest.MonkeyPatch) -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("a_category_with_no_entries",),
    )
    _patch_chat_model(monkeypatch, "This sounds urgent.")

    response = await build_guardrail_response(match, "some message")

    assert response == "This sounds urgent."


async def test_llm_service_receives_the_original_message_for_language_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    model = _patch_chat_model(monkeypatch)

    await build_guardrail_response(match, "Écris-moi un poème.")

    assert "Écris-moi un poème." in _sent_prompt(model)


@pytest.mark.parametrize("blank_content", ["", "   "])
async def test_response_raises_when_localization_response_is_blank_and_no_resources_exist(
    monkeypatch: pytest.MonkeyPatch,
    blank_content: str,
) -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    _patch_chat_model(monkeypatch, blank_content)

    with pytest.raises(RuntimeError):
        await build_guardrail_response(match, "some message")


async def test_response_raises_when_localization_call_fails_and_no_resources_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    _patch_chat_model(monkeypatch, raises=True)

    with pytest.raises(RuntimeError):
        await build_guardrail_response(match, "some message")


async def test_crisis_response_falls_back_to_safe_intro_when_localization_response_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crisis match must still surface its resources even if the intro call itself fails."""
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis", "emergency"),
    )
    _patch_chat_model(monkeypatch, "")

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert response.startswith("Please contact one of these services:\n\n")
    assert "MIELI Crisis Helpline" in response
    assert "General emergency number (112)" in response


async def test_crisis_response_falls_back_to_safe_intro_when_localization_call_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same fallback applies when the intro call raises outright, not just a blank response."""
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis", "emergency"),
    )
    _patch_chat_model(monkeypatch, raises=True)

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert response.startswith("Please contact one of these services:\n\n")
    assert "MIELI Crisis Helpline" in response
    assert "General emergency number (112)" in response


async def test_legal_sensitive_response_falls_back_to_safe_intro_when_localization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.LEGAL_SENSITIVE,
        reason="asylum process",
        resource_categories=("legal_aid", "immigration_authority"),
    )
    _patch_chat_model(monkeypatch, raises=True)

    response = await build_guardrail_response(match, "I was denied asylum.")

    assert response.startswith("Please contact one of these services:\n\n")
    assert "Oikeusapu" in response


async def test_localized_intro_uses_a_bounded_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The timeout is enforced by the model's own client (see its tests), not here — this
    only checks the value actually reaches the model built for the intro call."""
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    build_chat_model_calls: list[tuple[object, ...]] = []

    def fake_build_chat_model(*args: object, **kwargs: object) -> Mock:
        build_chat_model_calls.append((args, kwargs))
        model = Mock(spec=BaseChatModel)
        model.invoke.return_value = AIMessage(content="Localized intro text.")
        return model

    monkeypatch.setattr("app.guardrails.responses.build_chat_model", fake_build_chat_model)

    await build_guardrail_response(match, "some message")

    assert len(build_chat_model_calls) == 1
    _args, kwargs = build_chat_model_calls[0]
    assert kwargs["timeout"] == _INTRO_TIMEOUT_SECONDS


async def test_crisis_resources_withheld_when_gate_enabled_and_status_not_approved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The require_approved_crisis_resources fail-closed path withholds specific contacts."""
    monkeypatch.setenv("TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES", "true")
    monkeypatch.setattr("app.guardrails.responses.load_crisis_resources", lambda: _DRAFT_RESOURCE_LIST)
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis",),
    )
    model = _patch_chat_model(monkeypatch, "Please contact emergency services.")

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert "Test Crisis Line" not in response
    assert "000" not in response
    assert "aren't available right now" in _sent_prompt(model)


async def test_crisis_resources_shown_when_gate_enabled_and_status_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate only withholds non-approved lists — an approved list still surfaces contacts."""
    approved_list = CrisisResourceList(version=1, status="approved", resources=_DRAFT_RESOURCE_LIST.resources)
    monkeypatch.setenv("TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES", "true")
    monkeypatch.setattr("app.guardrails.responses.load_crisis_resources", lambda: approved_list)
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis",),
    )
    _patch_chat_model(monkeypatch, "Please contact emergency services.")

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert "Test Crisis Line" in response


async def test_crisis_resources_shown_when_gate_disabled_regardless_of_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default (gate disabled) preserves existing behavior: draft data is still shown."""
    monkeypatch.setenv("TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES", "false")
    monkeypatch.setattr("app.guardrails.responses.load_crisis_resources", lambda: _DRAFT_RESOURCE_LIST)
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis",),
    )
    _patch_chat_model(monkeypatch, "Please contact emergency services.")

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert "Test Crisis Line" in response


async def test_crisis_response_uses_no_resources_fallback_when_unmatched_and_localization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crisis match with no matching resource category must not surface a bare generic error."""
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("a_category_with_no_entries",),
    )
    _patch_chat_model(monkeypatch, raises=True)

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert response == "Please contact your local emergency services or a trusted support line directly."


async def test_crisis_response_uses_no_resources_fallback_when_gate_withholds_and_localization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same fallback applies when the gate, not an unmatched category, is why there are no resources."""
    monkeypatch.setenv("TAPIO_BACKEND_REQUIRE_APPROVED_CRISIS_RESOURCES", "true")
    monkeypatch.setattr("app.guardrails.responses.load_crisis_resources", lambda: _DRAFT_RESOURCE_LIST)
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis",),
    )
    _patch_chat_model(monkeypatch, raises=True)

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert response == "Please contact your local emergency services or a trusted support line directly."


async def test_legal_sensitive_response_uses_no_resources_fallback_when_unmatched_and_localization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.LEGAL_SENSITIVE,
        reason="asylum process",
        resource_categories=("a_category_with_no_entries",),
    )
    _patch_chat_model(monkeypatch, raises=True)

    response = await build_guardrail_response(match, "I was denied asylum.")

    assert response == "Please contact your local emergency services or a trusted support line directly."
