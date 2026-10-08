"""Schema-constrained chat model calls that report failure as a value (#140).

``BaseChatModel.with_structured_output(schema)`` already constrains a call to a
Pydantic schema uniformly across ``ChatOllama``, ``ChatOpenAI``, and
``ChatAnthropic``. What it leaves to every call site is what a failure means.
The providers don't even fail alike: Ollama raises ``OutputParserException``
for malformed JSON, OpenAI raises ``OpenAIRefusalError`` or a ``ValueError``
when no parsed object comes back, and Anthropic returns ``None`` when the model
answers in prose instead of calling the schema tool. ``StructuredOutputModel``
folds all of that into one ``StructuredOutputResult`` with two kinds of failure,
because they carry different information:

- An **infra failure** (connection error, timeout, a server-level error
  response) says nothing about the input. Retrying won't help, and the caller's
  next model call will likely hit the same failure, so it is returned at once.
- A **parse failure** (the model responded, but its output didn't fit the
  schema, including a schema validator rejecting it) is specific to that one
  response, so it is retried before being reported. A single malformed response
  is common and often succeeds on retry; a repeated one is a real signal about
  that input.

Any exception that isn't a known infra error type is treated as a parse
failure, since each provider's parser raises its own type.

What a failure means for the turn (fail open, escalate, fall back to fixed copy)
is the caller's policy, not this module's: the guardrail classifier and the
guardrail response intro decide differently from the same result.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from pydantic import BaseModel

from app.services.llm_providers import PROVIDERS

logger = logging.getLogger(__name__)

# Each provider's SDK wraps connection failures in its own exception type rather than
# raising a raw httpx error (see app.services.llm_providers.PROVIDERS for the
# per-provider types). httpx.RequestError and TimeoutError aren't provider-specific:
# Ollama's client raises them directly for a connection failure or a stalled request,
# and asyncio.timeout raises TimeoutError. Without these, an infra failure would be
# retried and reported as a parse failure.
INFRA_ERROR_TYPES: Final[tuple[type[BaseException], ...]] = (
    httpx.RequestError,
    TimeoutError,
    *(error_type for provider in PROVIDERS.values() for error_type in provider.infra_error_types),
)


class StructuredOutputFailure(StrEnum):
    """Why a structured-output call produced no schema-valid value."""

    INFRA = "infra"
    PARSE = "parse"


@dataclass(frozen=True, slots=True)
class StructuredOutputResult[SchemaT: BaseModel]:
    """The outcome of a structured-output call: a valid value, or why there isn't one.

    Args:
        value: The schema-valid result, or ``None`` on failure.
        failure: ``None`` on success, otherwise the kind of failure.
        error: The exception behind the last failed attempt, for logging or chaining.
        attempts: How many model calls were made.
    """

    value: SchemaT | None = None
    failure: StructuredOutputFailure | None = None
    error: BaseException | None = None
    attempts: int = 1

    @property
    def ok(self) -> bool:
        """True when ``value`` holds a schema-valid result."""
        return self.failure is None


class StructuredOutputModel[SchemaT: BaseModel]:
    """A chat model bound to ``schema`` whose calls return a ``StructuredOutputResult``."""

    def __init__(
        self,
        model: BaseChatModel,
        schema: type[SchemaT],
        *,
        parse_retries: int = 1,
        timeout: float | None = None,
    ) -> None:
        """Bind ``schema`` onto ``model``.

        Args:
            model: A chat model built by ``app.services.chat_model.build_chat_model``.
            schema: The Pydantic model each response must validate against, including
                any field validators it declares.
            parse_retries: How many extra calls to make after a parse failure.
            timeout: Optional per-call bound in seconds for ``ainvoke``. ``invoke`` can't
                enforce one from outside the call, so a synchronous caller relies on the
                timeout baked into ``model`` by ``build_chat_model(timeout=...)``.
        """
        self._schema = schema
        self._runnable = model.with_structured_output(schema)
        self._max_attempts = parse_retries + 1
        self._timeout = timeout

    def invoke(self, model_input: LanguageModelInput) -> StructuredOutputResult[SchemaT]:
        """Call the model, retrying on a parse failure.

        Args:
            model_input: A prompt string or a messages list.

        Returns:
            The schema-valid value, or the failure that prevented one.
        """
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                value = self._validated(self._runnable.invoke(model_input))
            except INFRA_ERROR_TYPES as error:
                return self._infra_failure(error, attempt)
            except Exception as error:  # Each provider's parser raises its own type.
                last_error = self._parse_failure(error, attempt)
            else:
                return StructuredOutputResult(value=value, attempts=attempt)
        return StructuredOutputResult(
            failure=StructuredOutputFailure.PARSE, error=last_error, attempts=self._max_attempts
        )

    async def ainvoke(self, model_input: LanguageModelInput) -> StructuredOutputResult[SchemaT]:
        """Call the model asynchronously, retrying on a parse failure.

        Args:
            model_input: A prompt string or a messages list.

        Returns:
            The schema-valid value, or the failure that prevented one.
        """
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with asyncio.timeout(self._timeout):
                    value = self._validated(await self._runnable.ainvoke(model_input))
            except INFRA_ERROR_TYPES as error:
                return self._infra_failure(error, attempt)
            except Exception as error:  # Each provider's parser raises its own type.
                last_error = self._parse_failure(error, attempt)
            else:
                return StructuredOutputResult(value=value, attempts=attempt)
        return StructuredOutputResult(
            failure=StructuredOutputFailure.PARSE, error=last_error, attempts=self._max_attempts
        )

    def _validated(self, raw: object) -> SchemaT:
        # Anthropic's tool parser returns None, rather than raising, when the model answers
        # in prose instead of calling the schema tool.
        if not isinstance(raw, self._schema):
            msg = f"Expected {self._schema.__name__}, got {type(raw).__name__}"
            raise TypeError(msg)
        return raw

    def _infra_failure(self, error: BaseException, attempt: int) -> StructuredOutputResult[SchemaT]:
        logger.warning("Structured output for %s failed (infra): %r", self._schema.__name__, error)
        return StructuredOutputResult(failure=StructuredOutputFailure.INFRA, error=error, attempts=attempt)

    def _parse_failure(self, error: Exception, attempt: int) -> Exception:
        logger.info(
            "Structured output for %s did not fit the schema (attempt %d of %d): %r",
            self._schema.__name__,
            attempt,
            self._max_attempts,
            error,
        )
        return error
