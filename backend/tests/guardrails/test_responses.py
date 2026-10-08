"""Tests for guardrail interception copy (#29)."""

import json

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_ollama import ChatOllama
from pydantic import Field, ValidationError

from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.guardrails.resources import CrisisResource, CrisisResourceList
from app.guardrails.responses import _INTRO_TIMEOUT_SECONDS, GuardrailIntro, build_guardrail_response

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


class _IntroModel(ChatOllama):
    """A real ``ChatOllama`` whose provider call is replaced, so the structured-output chain still runs.

    Each reply is the intro text the model "writes", returned as the JSON object Ollama's
    structured-output mode produces; the last reply repeats once the list runs out.
    """

    replies: list[str] = Field(default_factory=list)
    raises: bool = False
    received: list[list[BaseMessage]] = Field(default_factory=list)

    async def _agenerate(self, messages: list[BaseMessage], *args: object, **kwargs: object) -> ChatResult:
        self.received.append(messages)
        if self.raises:
            msg = "The model call failed."
            raise RuntimeError(msg)
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps({"text": text})))])


def _patch_chat_model(
    monkeypatch: pytest.MonkeyPatch,
    intro_text: str | list[str] = "Localized intro text.",
    *,
    raises: bool = False,
) -> _IntroModel:
    """Patch the model ``_localized_intro`` builds for itself, and return it for assertions.

    ``build_guardrail_response`` builds its own short-timeout model per call (see
    ``app.guardrails.responses._localized_intro``) rather than taking an injected one, so
    tests control its behavior by patching the factory function it calls.
    """
    replies = [intro_text] if isinstance(intro_text, str) else intro_text
    model = _IntroModel(model="test-model", replies=replies, raises=raises)
    monkeypatch.setattr("app.guardrails.responses.build_chat_model", lambda *_args, **_kwargs: model)
    return model


def _sent_prompt(model: _IntroModel) -> str:
    """Extract the prompt text ``_localized_intro`` sent to the model."""
    return str(model.received[-1][-1].content)


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


@pytest.mark.parametrize(
    "text",
    [
        "Visit https://example.fi for help.",
        "See www.example.com.",
        "Katso lisää osoitteesta kela.fi.",
        "Write to help@example.org.",
        "Soita numeroon 09 2525 0111.",
        "Call 112 right away.",
        "Ring +358 40 123 4567.",
    ],
)
def test_guardrail_intro_rejects_contact_details(text: str) -> None:
    with pytest.raises(ValidationError):
        GuardrailIntro(text=text)


@pytest.mark.parametrize("text", ["", "   "])
def test_guardrail_intro_rejects_a_blank_intro(text: str) -> None:
    with pytest.raises(ValidationError):
        GuardrailIntro(text=text)


@pytest.mark.parametrize(
    "text",
    [
        "This sounds urgent. Please reach out to one of the services below.",
        "Tämä kuulostaa kiireelliseltä. Ota yhteyttä alla oleviin palveluihin.",
        "Det här låter brådskande, och hjälpen nedan finns tillgänglig 24/7.",
        "هذا يبدو عاجلاً. يرجى التواصل مع إحدى الخدمات أدناه.",
    ],
)
def test_guardrail_intro_accepts_plain_text_in_any_language(text: str) -> None:
    assert GuardrailIntro(text=f"  {text}  ").text == text


async def test_crisis_response_retries_an_intro_containing_a_phone_number(monkeypatch: pytest.MonkeyPatch) -> None:
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis", "emergency"),
    )
    model = _patch_chat_model(monkeypatch, ["Call 0800 123 456 now.", "This sounds urgent."])

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert response.startswith("This sounds urgent.\n\n")
    assert "0800 123 456" not in response
    assert len(model.received) == 2


async def test_crisis_response_falls_back_when_every_intro_contains_contact_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that keeps writing its own contact details never gets them shown."""
    match = GuardrailMatch(
        category=GuardrailCategory.CRISIS,
        reason="risk to life",
        resource_categories=("mental_health_crisis", "emergency"),
    )
    _patch_chat_model(monkeypatch, "Call the helpline at 0800 123 456 or visit https://made-up.example.")

    response = await build_guardrail_response(match, "I want to kill myself.")

    assert response.startswith("Please contact one of these services:\n\n")
    assert "0800 123 456" not in response
    assert "made-up.example" not in response
    assert "MIELI Crisis Helpline" in response


async def test_out_of_scope_response_raises_when_every_intro_contains_contact_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = GuardrailMatch(category=GuardrailCategory.OUT_OF_SCOPE, reason="off-topic")
    _patch_chat_model(monkeypatch, "Try https://www.example.com instead.")

    with pytest.raises(RuntimeError):
        await build_guardrail_response(match, "Write me a poem.")


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

    def fake_build_chat_model(*args: object, **kwargs: object) -> _IntroModel:
        build_chat_model_calls.append((args, kwargs))
        return _IntroModel(model="test-model", replies=["Localized intro text."])

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
