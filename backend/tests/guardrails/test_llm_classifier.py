"""Tests for the parallel, structured-output LLM guardrail classification stage (#29)."""

from collections.abc import Sequence
from types import SimpleNamespace

import httpx
import ollama
import pytest
from langchain_ollama import ChatOllama

from app.guardrails import GuardrailCategory, LLMGuardrailClassifier
from app.guardrails.llm_classifier import GuardrailCheckResult, _ParseError

_NO_MATCH = GuardrailCheckResult(match=False, subtype="none", reason="")

_CheckOutcome = GuardrailCheckResult | Exception
_INFRA_ERRORS = [
    httpx.ConnectError("boom"),
    httpx.TimeoutException("boom"),
    ollama.ResponseError("boom"),
    TimeoutError(),
]


def _build_classifier(
    *,
    crisis: _CheckOutcome | Sequence[_CheckOutcome],
    legal_sensitive: _CheckOutcome | Sequence[_CheckOutcome],
    out_of_scope: _CheckOutcome | Sequence[_CheckOutcome],
) -> LLMGuardrailClassifier:
    """Build a real LLMGuardrailClassifier with its structured model stubbed per check.

    ``model.with_structured_output(...)`` is lazily bound (no network call at construction
    time), so the classifier itself is real; only the structured runnable is replaced, so
    tests exercise the classifier's own routing/priority/retry logic, not the mock. Which
    concrete ``BaseChatModel`` is passed in doesn't matter here since it's never actually
    invoked; ``ChatOllama`` is just a cheap, already-a-dependency stand-in.

    Each of ``crisis``/``legal_sensitive``/``out_of_scope`` is a ``GuardrailCheckResult`` to
    return, an ``Exception`` instance to raise, or a sequence of either — consumed in order
    across that check's calls (the classifier retries once on a parse-type failure), with the
    last item repeating if the check is called more times than the sequence has entries.
    """
    classifier = LLMGuardrailClassifier(ChatOllama(model="test-model"))

    def _as_queue(outcome: _CheckOutcome | Sequence[_CheckOutcome]) -> list[_CheckOutcome]:
        if isinstance(outcome, GuardrailCheckResult | Exception):
            return [outcome]
        return list(outcome)

    queues = {
        "crisis": _as_queue(crisis),
        "legal_sensitive": _as_queue(legal_sensitive),
        "out_of_scope": _as_queue(out_of_scope),
    }

    async def fake_ainvoke(prompt: str) -> GuardrailCheckResult:
        if "self-harm or" in prompt:
            key = "crisis"
        elif "asylum, deportation" in prompt:
            key = "legal_sensitive"
        elif "completely unrelated" in prompt:
            key = "out_of_scope"
        else:
            msg = f"Unexpected prompt in test double: {prompt!r}"
            raise AssertionError(msg)

        queue = queues[key]
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
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


@pytest.mark.parametrize("infra_error", _INFRA_ERRORS)
async def test_classify_fails_open_immediately_on_infra_error_without_retry(infra_error: Exception) -> None:
    """A connection/timeout/server-level error is message-independent — fail open with no retry."""
    calls: list[str] = []
    classifier = _build_classifier(crisis=infra_error, legal_sensitive=_NO_MATCH, out_of_scope=_NO_MATCH)
    real_ainvoke = classifier._structured_model.ainvoke

    async def counting_ainvoke(prompt: str) -> GuardrailCheckResult:
        if "self-harm or" in prompt:
            calls.append(prompt)
        return await real_ainvoke(prompt)

    classifier._structured_model = SimpleNamespace(ainvoke=counting_ainvoke)

    result = await classifier.classify("some message")

    assert result is None
    assert len(calls) == 1  # no retry for an infra-classified failure


async def test_classify_retries_once_on_parse_error_and_uses_the_retry_result() -> None:
    """A single malformed response is retried, not treated as a confirmed failure."""
    classifier = _build_classifier(
        crisis=[
            ValueError("could not parse structured output"),
            GuardrailCheckResult(match=True, subtype="self_harm", reason="Message expresses self-harm intent."),
        ],
        legal_sensitive=_NO_MATCH,
        out_of_scope=_NO_MATCH,
    )

    result = await classifier.classify("some message")

    assert result is not None
    assert result.category is GuardrailCategory.CRISIS
    assert result.reason == "Message expresses self-harm intent."


async def test_classify_fails_open_when_the_retry_hits_an_infra_error() -> None:
    """A parse failure followed by an infra failure on retry still fails open — no escalation."""
    classifier = _build_classifier(
        crisis=[ValueError("could not parse structured output"), httpx.ConnectError("boom")],
        legal_sensitive=_NO_MATCH,
        out_of_scope=_NO_MATCH,
    )

    result = await classifier.classify("some message")

    assert result is None


async def test_classify_escalates_crisis_after_two_consecutive_parse_errors() -> None:
    """Two parse failures in a row on the crisis check is a real signal, not noise — escalate."""
    classifier = _build_classifier(
        crisis=[ValueError("bad json 1"), ValueError("bad json 2")],
        legal_sensitive=_NO_MATCH,
        out_of_scope=_NO_MATCH,
    )

    result = await classifier.classify("some message")

    assert result is not None
    assert result.category is GuardrailCategory.CRISIS
    assert result.resource_categories == ("emergency",)


async def test_classify_fails_open_after_two_consecutive_parse_errors_for_non_crisis_checks() -> None:
    """Only the crisis check escalates on a repeated parse failure — the others still fail open."""
    classifier = _build_classifier(
        crisis=_NO_MATCH,
        legal_sensitive=[ValueError("bad json 1"), ValueError("bad json 2")],
        out_of_scope=_NO_MATCH,
    )

    result = await classifier.classify("some message")

    assert result is None


@pytest.mark.parametrize("subtype", ["none", "unexpected_value", ""])
async def test_classify_never_returns_a_crisis_match_with_zero_resources(subtype: str) -> None:
    """A positive crisis match must always carry at least the emergency resource category."""
    classifier = _build_classifier(
        crisis=GuardrailCheckResult(match=True, subtype=subtype, reason="crisis"),
        legal_sensitive=_NO_MATCH,
        out_of_scope=_NO_MATCH,
    )

    result = await classifier.classify("some message")

    assert result is not None
    assert result.category is GuardrailCategory.CRISIS
    assert result.resource_categories != ()
    assert "emergency" in result.resource_categories


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


async def test_invoke_treats_an_unexpected_result_type_as_a_parse_error() -> None:
    """`with_structured_output` is expected to return a GuardrailCheckResult; anything else is a parse failure."""
    classifier = LLMGuardrailClassifier(ChatOllama(model="test-model"))

    async def fake_ainvoke(prompt: str) -> dict[str, bool]:
        return {"match": True}

    classifier._structured_model = SimpleNamespace(ainvoke=fake_ainvoke)

    with pytest.raises(_ParseError):
        await classifier._invoke("prompt")
