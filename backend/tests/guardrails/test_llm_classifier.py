"""Tests for the parallel, structured-output LLM guardrail classification stage (#29)."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.guardrails import GuardrailCategory, LLMGuardrailClassifier
from app.guardrails.llm_classifier import GuardrailCheckResult

_NO_MATCH = GuardrailCheckResult(match=False, subtype="none", reason="")


def _build_classifier(*, crisis: Any, legal_sensitive: Any, out_of_scope: Any) -> LLMGuardrailClassifier:
    """Build a real LLMGuardrailClassifier with its structured model stubbed per check.

    ``ChatOllama(...).with_structured_output(...)`` is lazily bound (no network call at
    construction time), so the classifier itself is real; only the structured runnable is
    replaced, so tests exercise the classifier's own routing/priority logic, not the mock.

    Each of ``crisis``/``legal_sensitive``/``out_of_scope`` is either a ``GuardrailCheckResult``
    to return or an ``Exception`` instance to raise, standing in for that check's model call.
    """
    classifier = LLMGuardrailClassifier(model_name="test-model")

    async def fake_ainvoke(prompt: str) -> GuardrailCheckResult:
        if "self-harm or" in prompt:
            outcome = crisis
        elif "asylum, deportation" in prompt:
            outcome = legal_sensitive
        elif "completely unrelated" in prompt:
            outcome = out_of_scope
        else:
            msg = f"Unexpected prompt in test double: {prompt!r}"
            raise AssertionError(msg)

        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    classifier._structured_model = SimpleNamespace(ainvoke=fake_ainvoke)
    return classifier


async def test_classify_returns_none_when_no_check_matches() -> None:
    classifier = _build_classifier(crisis=_NO_MATCH, legal_sensitive=_NO_MATCH, out_of_scope=_NO_MATCH)

    result = await classifier.classify("How do I renew my residence permit?")

    assert result is None


async def test_classify_runs_all_three_checks() -> None:
    """All three checks must run for every message — the priority resolution needs all results."""
    calls: list[str] = []
    classifier = _build_classifier(crisis=_NO_MATCH, legal_sensitive=_NO_MATCH, out_of_scope=_NO_MATCH)

    async def counting_ainvoke(prompt: str) -> GuardrailCheckResult:
        calls.append(prompt)
        return _NO_MATCH

    classifier._structured_model = SimpleNamespace(ainvoke=counting_ainvoke)

    await classifier.classify("Anything")

    assert len(calls) == 3


async def test_classify_maps_crisis_subtype_to_resource_categories() -> None:
    classifier = _build_classifier(
        crisis=GuardrailCheckResult(match=True, subtype="self_harm", reason="Message expresses self-harm intent."),
        legal_sensitive=_NO_MATCH,
        out_of_scope=_NO_MATCH,
    )

    result = await classifier.classify("some message")

    assert result is not None
    assert result.category is GuardrailCategory.CRISIS
    assert result.reason == "Message expresses self-harm intent."
    assert result.resource_categories == ("mental_health_crisis", "emergency")


async def test_classify_prefers_crisis_when_multiple_checks_match() -> None:
    classifier = _build_classifier(
        crisis=GuardrailCheckResult(match=True, subtype="emergency", reason="emergency"),
        legal_sensitive=GuardrailCheckResult(match=True, subtype="legal", reason="legal"),
        out_of_scope=_NO_MATCH,
    )

    result = await classifier.classify("some message")

    assert result is not None
    assert result.category is GuardrailCategory.CRISIS


@pytest.mark.parametrize("failure", [RuntimeError("model unreachable"), ValueError("bad schema")])
async def test_classify_fails_open_when_a_check_errors(failure: Exception) -> None:
    classifier = _build_classifier(crisis=failure, legal_sensitive=_NO_MATCH, out_of_scope=_NO_MATCH)

    result = await classifier.classify("some message")

    assert result is None


async def test_classify_defaults_legal_sensitive_resources_when_subtype_unrecognized() -> None:
    classifier = _build_classifier(
        crisis=_NO_MATCH,
        legal_sensitive=GuardrailCheckResult(match=True, subtype="unexpected_value", reason="legal"),
        out_of_scope=_NO_MATCH,
    )

    result = await classifier.classify("some message")

    assert result is not None
    assert result.category is GuardrailCategory.LEGAL_SENSITIVE
    assert result.resource_categories == ("legal_aid", "immigration_authority")


async def test_classify_falls_back_to_generated_reason_when_reason_is_blank() -> None:
    classifier = _build_classifier(
        crisis=_NO_MATCH,
        legal_sensitive=_NO_MATCH,
        out_of_scope=GuardrailCheckResult(match=True, subtype="none", reason=""),
    )

    result = await classifier.classify("some message")

    assert result is not None
    assert result.reason == "LLM classified as out_of_scope (none)."
