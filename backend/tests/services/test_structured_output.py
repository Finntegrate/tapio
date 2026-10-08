"""Tests for the shared structured-output wrapper (#140).

Each supported provider is exercised through its real ``with_structured_output``
chain; only the provider's ``_generate``/``_agenerate`` is replaced, returning the
response shape that provider actually produces. That keeps each provider's own
parser in the loop, which is where they differ: Ollama parses JSON content, OpenAI
reads the SDK's ``parsed`` object (or a ``refusal``), and Anthropic reads a tool call.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import anthropic
import httpx
import ollama
import openai
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, field_validator

from app.services.structured_output import (
    StructuredOutputFailure,
    StructuredOutputModel,
    StructuredOutputResult,
)

_KNOWN_GUIDES = frozenset({"ilmarinen", "sampo"})


class Answer(BaseModel):
    """A small schema with a validator, standing in for a real routing decision."""

    guide: str
    confident: bool

    @field_validator("guide")
    @classmethod
    def _known_guide(cls, value: str) -> str:
        if value not in _KNOWN_GUIDES:
            msg = f"Unknown guide {value!r}"
            raise ValueError(msg)
        return value


_VALID = {"guide": "ilmarinen", "confident": True}
_WRONG_TYPES = {"guide": 5, "confident": "maybe"}
_REJECTED_BY_VALIDATOR = {"guide": "nobody", "confident": True}

# A reply is a message, an exception the provider call raises, or a callable building
# the message at call time (so a provider-side validation error raises during the call).
_Reply = AIMessage | Exception | Callable[[], AIMessage]


@dataclass(frozen=True)
class _Provider:
    """How one provider shapes a structured response, and the errors its SDK raises."""

    name: str
    model_cls: type[BaseChatModel]
    build: Callable[[], BaseChatModel]
    respond: Callable[[dict[str, Any]], _Reply]
    prose: _Reply
    infra_error: Exception


def _openai_respond(payload: dict[str, Any]) -> Callable[[], AIMessage]:
    # The OpenAI SDK's parse() validates against the schema itself and raises on a
    # mismatch, so the validation runs during the call, as it does for real.
    return lambda: AIMessage(content=json.dumps(payload), additional_kwargs={"parsed": Answer.model_validate(payload)})


_PROVIDERS = [
    _Provider(
        name="ollama",
        model_cls=ChatOllama,
        build=lambda: ChatOllama(model="test-model"),
        respond=lambda payload: AIMessage(content=json.dumps(payload)),
        prose=AIMessage(content="Sure! Ilmarinen should answer this one."),
        infra_error=ollama.ResponseError("model not found"),
    ),
    _Provider(
        name="openai",
        model_cls=ChatOpenAI,
        build=lambda: ChatOpenAI(model="gpt-test", api_key="test-key"),
        respond=_openai_respond,
        prose=AIMessage(content="", additional_kwargs={"refusal": "I can't help with that."}),
        infra_error=openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1")),
    ),
    _Provider(
        name="anthropic",
        model_cls=ChatAnthropic,
        build=lambda: ChatAnthropic(model="claude-test", api_key="test-key"),
        respond=lambda payload: AIMessage(content="", tool_calls=[{"name": "Answer", "args": payload, "id": "call_1"}]),
        prose=AIMessage(content="Sure! Ilmarinen should answer this one."),
        infra_error=anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1")),
    ),
]

_Mode = Literal["sync", "async"]


@pytest.fixture(params=_PROVIDERS, ids=lambda provider: provider.name)
def provider(request: pytest.FixtureRequest) -> _Provider:
    return request.param


@pytest.fixture(params=["sync", "async"])
def mode(request: pytest.FixtureRequest) -> _Mode:
    return request.param


def _stub_replies(monkeypatch: pytest.MonkeyPatch, provider: _Provider, replies: list[_Reply]) -> list[int]:
    """Make ``provider``'s model return ``replies`` in order, and count its calls.

    Returns:
        A list that grows by one entry per model call.
    """
    calls: list[int] = []
    queue = list(replies)

    def next_result() -> ChatResult:
        calls.append(1)
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        message = reply() if callable(reply) else reply
        return ChatResult(generations=[ChatGeneration(message=message)])

    def fake_generate(self: BaseChatModel, *args: object, **kwargs: object) -> ChatResult:
        return next_result()

    async def fake_agenerate(self: BaseChatModel, *args: object, **kwargs: object) -> ChatResult:
        return next_result()

    monkeypatch.setattr(provider.model_cls, "_generate", fake_generate)
    monkeypatch.setattr(provider.model_cls, "_agenerate", fake_agenerate)
    return calls


async def _call(model: StructuredOutputModel[Answer], mode: _Mode) -> StructuredOutputResult[Answer]:
    if mode == "sync":
        return model.invoke("Which guide handles residence permits?")
    return await model.ainvoke("Which guide handles residence permits?")


async def test_returns_the_parsed_value_for_a_valid_response(
    monkeypatch: pytest.MonkeyPatch, provider: _Provider, mode: _Mode
) -> None:
    calls = _stub_replies(monkeypatch, provider, [provider.respond(_VALID)])

    result = await _call(StructuredOutputModel(provider.build(), Answer), mode)

    assert result.ok
    assert result.value == Answer(guide="ilmarinen", confident=True)
    assert result.failure is None
    assert result.attempts == 1
    assert len(calls) == 1


@pytest.mark.parametrize("shape", ["wrong_types", "rejected_by_validator", "prose"])
async def test_reports_a_parse_failure_after_retrying_an_invalid_response(
    monkeypatch: pytest.MonkeyPatch, provider: _Provider, mode: _Mode, shape: str
) -> None:
    """Every provider's own way of failing to fit the schema is a parse failure, never a raise."""
    reply = {
        "wrong_types": provider.respond(_WRONG_TYPES),
        "rejected_by_validator": provider.respond(_REJECTED_BY_VALIDATOR),
        "prose": provider.prose,
    }[shape]
    calls = _stub_replies(monkeypatch, provider, [reply])

    result = await _call(StructuredOutputModel(provider.build(), Answer), mode)

    assert not result.ok
    assert result.value is None
    assert result.failure is StructuredOutputFailure.PARSE
    assert result.error is not None
    assert result.attempts == 2
    assert len(calls) == 2


async def test_uses_the_retry_when_only_the_first_response_is_invalid(
    monkeypatch: pytest.MonkeyPatch, provider: _Provider, mode: _Mode
) -> None:
    _stub_replies(monkeypatch, provider, [provider.prose, provider.respond(_VALID)])

    result = await _call(StructuredOutputModel(provider.build(), Answer), mode)

    assert result.ok
    assert result.value == Answer(guide="ilmarinen", confident=True)
    assert result.attempts == 2


async def test_reports_an_infra_failure_without_retrying(
    monkeypatch: pytest.MonkeyPatch, provider: _Provider, mode: _Mode
) -> None:
    calls = _stub_replies(monkeypatch, provider, [provider.infra_error])

    result = await _call(StructuredOutputModel(provider.build(), Answer), mode)

    assert result.failure is StructuredOutputFailure.INFRA
    assert result.error is provider.infra_error
    assert result.attempts == 1
    assert len(calls) == 1


@pytest.mark.parametrize("infra_error", [httpx.ConnectError("refused"), TimeoutError()])
async def test_treats_transport_errors_as_infra_for_any_provider(
    monkeypatch: pytest.MonkeyPatch, provider: _Provider, mode: _Mode, infra_error: Exception
) -> None:
    _stub_replies(monkeypatch, provider, [infra_error])

    result = await _call(StructuredOutputModel(provider.build(), Answer), mode)

    assert result.failure is StructuredOutputFailure.INFRA


async def test_an_infra_failure_on_the_retry_is_reported_as_infra(
    monkeypatch: pytest.MonkeyPatch, provider: _Provider, mode: _Mode
) -> None:
    _stub_replies(monkeypatch, provider, [provider.prose, provider.infra_error])

    result = await _call(StructuredOutputModel(provider.build(), Answer), mode)

    assert result.failure is StructuredOutputFailure.INFRA
    assert result.attempts == 2


async def test_parse_retries_sets_how_many_extra_calls_are_made(
    monkeypatch: pytest.MonkeyPatch, provider: _Provider, mode: _Mode
) -> None:
    calls = _stub_replies(monkeypatch, provider, [provider.prose])

    result = await _call(StructuredOutputModel(provider.build(), Answer, parse_retries=0), mode)

    assert result.failure is StructuredOutputFailure.PARSE
    assert result.attempts == 1
    assert len(calls) == 1


async def test_ainvoke_reports_a_stalled_call_as_an_infra_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stalled_agenerate(self: BaseChatModel, *args: object, **kwargs: object) -> ChatResult:
        await asyncio.sleep(10)
        raise AssertionError

    monkeypatch.setattr(ChatOllama, "_agenerate", stalled_agenerate)

    result = await StructuredOutputModel(ChatOllama(model="test-model"), Answer, timeout=0.01).ainvoke("prompt")

    assert result.failure is StructuredOutputFailure.INFRA
    assert isinstance(result.error, TimeoutError)
    assert result.attempts == 1
