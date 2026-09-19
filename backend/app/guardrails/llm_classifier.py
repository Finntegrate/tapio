"""LLM-based input classifier for guardrailed queries (#29).

Runs three independent, narrowly-scoped classification checks — crisis,
legal-sensitive, out-of-scope — concurrently against the same configured chat
model (#9: whichever provider ``TAPIO_LLM_PROVIDER`` selects, not always
Ollama) the RAG pipeline uses. Each check is a focused yes/no question
grounded with a handful of few-shot examples, rather than a fixed
keyword/regex list: a hardcoded phrase list is brittle, English-only, and
doesn't scale to real phrasing, so the same illustrative phrases are given to
the model as examples instead, which generalizes to wording and languages the
examples don't literally contain.

Each check binds a Pydantic schema via LangChain's structured-output support
(``BaseChatModel.with_structured_output``) rather than asking for free-text
JSON and parsing it by hand — the model call itself is constrained to the
schema, and a failure to produce a valid instance raises instead of silently
returning malformed text to parse.

This is the shape a LangGraph input-classifier node is expected to take
once the app's graph migration lands: parallel branches feeding one
decision, run before the routing node.

A check's failure is not treated as one undifferentiated case. It is
split into two kinds (see ``_InfraError``/``_ParseError`` and
``_invoke``), because they carry different information and call for
different responses:

- An **infra failure** (connection error, timeout, a server-level error
  response) is message-independent — it says nothing about whether this
  particular message is a crisis, and it means the RAG pipeline's own
  generation call is likely to hit the same failure right after, ending
  the turn at the existing generic-error path anyway. These fail open
  immediately: the same degradation the RAG pipeline already has for an
  unreachable model, not a new failure mode.
- A **parse failure** (the model responded, but its output didn't fit the
  schema) means the model *was* reachable and *did* respond — this is
  specific to that one call, not evidence of an outage, so it's retried
  once before drawing any conclusion (a single malformed response is not
  unusual and often succeeds on retry). If the retry also fails to parse,
  that is a real, repeated signal that this check couldn't be completed
  for this specific message: for the crisis check, that surfaces as a
  conservative crisis match (with the general ``emergency`` resource)
  instead of silently falling through to an unguarded RAG answer. The
  other two checks still fail open on a repeated parse failure — missing
  an out-of-scope or legal-sensitive redirect is a much smaller cost than
  a missed crisis.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Final

import httpx
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.prompts import load_prompt
from app.services.llm_providers import PROVIDERS

# Each provider's SDK wraps connection failures in its own exception type rather than
# raising a raw httpx error (see app.services.llm_providers.PROVIDERS for the
# per-provider types, e.g. why openai/anthropic each list an APIStatusError alongside
# their APIConnectionError). httpx.RequestError and TimeoutError aren't provider-specific
# — Ollama's client raises them directly for a connection failure or a stalled request,
# without wrapping. Without these, an infra failure would fall through to _ParseError
# and, after a retry, the crisis check would escalate to a conservative match for an
# ordinary request instead of failing open like every other infra failure.
_PROVIDER_INFRA_ERROR_TYPES: Final[tuple[type[BaseException], ...]] = tuple(
    error_type for provider in PROVIDERS.values() for error_type in provider.infra_error_types
)
_INFRA_ERROR_TYPES: Final[tuple[type[BaseException], ...]] = (
    httpx.RequestError,
    TimeoutError,
    *_PROVIDER_INFRA_ERROR_TYPES,
)

logger = logging.getLogger(__name__)


class _InfraError(Exception):
    """A check's model call failed for reasons unrelated to the message itself."""


class _ParseError(Exception):
    """The model responded, but its output didn't fit the expected schema."""


class GuardrailCheckResult(BaseModel):
    """Structured output schema for one guardrail classification check."""

    match: bool = Field(description="Whether the message meets this check's stated criteria.")
    subtype: str = Field(description="One of the check's allowed subtype options, or 'none'.")
    reason: str = Field(description="One short phrase explaining the decision, or an empty string if match is false.")


_SUBTYPE_RESOURCE_CATEGORIES: Final[dict[str, tuple[str, ...]]] = {
    "self_harm": ("mental_health_crisis", "emergency"),
    "domestic_abuse": ("domestic_abuse_support", "emergency"),
    "crime_victim": ("crime_victim_support", "emergency"),
    "emergency": ("emergency",),
    "legal": ("legal_aid", "immigration_authority"),
}


@dataclass(frozen=True, slots=True)
class _CheckSpec:
    """One focused, independent classification question, grounded with examples."""

    category: GuardrailCategory
    criteria_description: str
    subtype_options: str
    positive_examples: tuple[str, ...]
    negative_examples: tuple[str, ...]
    default_resource_categories: tuple[str, ...] = ()

    def render_examples(self) -> str:
        """Format this check's few-shot examples as a prompt-ready block.

        Returns:
            A "does match" / "does not match" Markdown block for the prompt.
        """
        positive_lines = "\n".join(f'- "{example}"' for example in self.positive_examples)
        negative_lines = "\n".join(f'- "{example}"' for example in self.negative_examples)
        return f"Examples that DO match:\n{positive_lines}\n\nExamples that do NOT match:\n{negative_lines}"


_CHECKS: Final[tuple[_CheckSpec, ...]] = (
    _CheckSpec(
        category=GuardrailCategory.CRISIS,
        criteria_description=(
            "Does the message describe an immediate risk to life or safety — self-harm or "
            "suicide, domestic violence or abuse, being the victim of a crime such as assault or "
            "trafficking, or another emergency needing immediate human help?"
        ),
        subtype_options="self_harm|domestic_abuse|crime_victim|emergency|none",
        positive_examples=(
            "I want to kill myself and don't know who to talk to.",
            "My partner hits me and I'm scared to go home.",
            "I was sexually assaulted last week and don't know what to do.",
            "This is a medical emergency, please help me.",
        ),
        negative_examples=(
            "I read an article about mental health support services in Finland.",
            "What is the general emergency number in Finland?",
            "I'm researching domestic violence statistics for a university report.",
        ),
        # A positive crisis match must never resolve to zero resources, even if the model
        # returns an unrecognized or "none" subtype — falling back silently to no contacts
        # at all would be the worst outcome for a message already flagged as a crisis.
        default_resource_categories=("emergency",),
    ),
    _CheckSpec(
        category=GuardrailCategory.LEGAL_SENSITIVE,
        criteria_description=(
            "Does the message concern asylum, deportation, detention, or another legal "
            "immigration process where only a qualified legal adviser should give guidance?"
        ),
        subtype_options="legal|none",
        positive_examples=(
            "I applied for asylum and got a negative decision, what can I do?",
            "I'm worried about being deported next month.",
            "Migri put me in a detention centre, who can help?",
        ),
        negative_examples=(
            "How long does a residence permit application usually take?",
            "What documents do I need to apply for a work permit?",
        ),
        default_resource_categories=("legal_aid", "immigration_authority"),
    ),
    _CheckSpec(
        category=GuardrailCategory.OUT_OF_SCOPE,
        criteria_description=(
            "Is the message completely unrelated to settling in Finland (immigration, work, "
            "benefits, housing, daily life) — e.g. creative writing, general coding help, "
            "trivia, or another unrelated topic?"
        ),
        subtype_options="none",
        positive_examples=(
            "Can you write me a poem about autumn?",
            "Give me a recipe for pancakes.",
            "Write me a Python script to sort a list.",
        ),
        negative_examples=(
            "How do I apply for Kela benefits?",
            "What should I check in a rental agreement before signing?",
        ),
    ),
)

# Priority when more than one check matches: the most safety-critical wins (PRD §7.4).
_CATEGORY_PRIORITY: Final[tuple[GuardrailCategory, ...]] = (
    GuardrailCategory.CRISIS,
    GuardrailCategory.LEGAL_SENSITIVE,
    GuardrailCategory.OUT_OF_SCOPE,
)

# A stalled provider call must not leave a chat SSE stream open with no terminal event.
# Local Ollama CPU inference in manual testing took up to ~45s for a single check, so
# this is generous rather than tight; tune per deployment/model if it proves wrong either way.
_CHECK_TIMEOUT_SECONDS: Final[float] = 60.0


class LLMGuardrailClassifier:
    """Classify a message with three parallel, example-guided, structured-output LLM checks."""

    def __init__(self, model: BaseChatModel) -> None:
        """Bind the structured-output schema onto the shared, already-configured chat model.

        Args:
            model: The same ``BaseChatModel`` instance the RAG pipeline generates with (see
                ``app.services.chat_model.build_chat_model``), so classification and answer
                generation use the same configured provider/model/credentials (#9) — not
                always Ollama.
        """
        self._structured_model = model.with_structured_output(GuardrailCheckResult)

    async def classify(self, message: str) -> GuardrailMatch | None:
        """Run all three category checks concurrently and return the highest-priority match.

        Args:
            message: The user's raw message.

        Returns:
            The highest-priority ``GuardrailMatch`` among the checks that matched, or ``None``
            if no check matched (or every check failed open).
        """
        results = await asyncio.gather(*(self._run_check(check, message) for check in _CHECKS))
        matches = {match.category: match for match in results if match is not None}
        for category in _CATEGORY_PRIORITY:
            if category in matches:
                return matches[category]
        return None

    async def _run_check(self, check: _CheckSpec, message: str) -> GuardrailMatch | None:
        """Run one focused, structured-output classification check, retrying once on a parse failure.

        Args:
            check: The category-specific check to run.
            message: The user's raw message.

        Returns:
            A ``GuardrailMatch`` if the check matched; ``None`` if it cleanly didn't, or if it
            failed for infra reasons; or — for the crisis check only — a conservative crisis
            match if the response couldn't be parsed twice in a row. See the module docstring.
        """
        prompt = load_prompt(
            "guardrail_check",
            criteria_description=check.criteria_description,
            subtype_options=check.subtype_options,
            examples=check.render_examples(),
            message=message,
        )
        try:
            result = await self._invoke(prompt)
        except _InfraError:
            logger.warning("Guardrail check %s failed (infra); failing open.", check.category)
            return None
        except _ParseError:
            logger.info("Guardrail check %s got an unparseable response; retrying once.", check.category)
            try:
                result = await self._invoke(prompt)
            except _InfraError:
                logger.warning("Guardrail check %s retry failed (infra); failing open.", check.category)
                return None
            except _ParseError:
                return self._degraded_result(check)

        return self._to_match(check, result)

    async def _invoke(self, prompt: str) -> GuardrailCheckResult:
        """Call the structured-output model once, categorizing any failure.

        Args:
            prompt: The fully-rendered check prompt.

        Returns:
            The parsed, schema-valid result.

        Raises:
            _InfraError: A connection, timeout, or server-level failure — message-independent,
                and the same failure the RAG pipeline's own generation call would likely hit too.
            _ParseError: The model responded, but its output didn't fit the expected schema —
                specific to this call, not evidence that the model/connection is unreachable.
        """
        try:
            async with asyncio.timeout(_CHECK_TIMEOUT_SECONDS):
                result = await self._structured_model.ainvoke(prompt)
        except _INFRA_ERROR_TYPES as error:
            raise _InfraError from error
        except Exception as error:
            raise _ParseError from error

        if not isinstance(result, GuardrailCheckResult):
            msg = f"Unexpected structured-output result type: {type(result)!r}"
            raise _ParseError(msg)
        return result

    @staticmethod
    def _degraded_result(check: _CheckSpec) -> GuardrailMatch | None:
        """Resolve two consecutive parse failures: escalate for crisis, fail open otherwise.

        Args:
            check: The check that failed to produce a parseable result twice in a row.

        Returns:
            A conservative crisis ``GuardrailMatch`` if ``check`` was the crisis check,
            else ``None``.
        """
        if check.category is not GuardrailCategory.CRISIS:
            logger.warning(
                "Guardrail check %s failed to produce structured output after a retry; failing open.",
                check.category,
            )
            return None

        logger.warning(
            "Guardrail check %s failed to produce structured output after a retry; treating "
            "conservatively as a crisis rather than failing open.",
            check.category,
        )
        return GuardrailMatch(
            category=GuardrailCategory.CRISIS,
            reason="The safety check could not confirm this message was safe to route normally.",
            resource_categories=("emergency",),
        )

    @staticmethod
    def _to_match(check: _CheckSpec, result: GuardrailCheckResult) -> GuardrailMatch | None:
        """Convert a successfully parsed result into a ``GuardrailMatch``, or ``None``.

        Args:
            check: The check this result came from.
            result: The parsed, schema-valid model output.

        Returns:
            A ``GuardrailMatch`` if ``result.match`` is true, else ``None``.
        """
        if not result.match:
            return None

        subtype = result.subtype.strip().lower()
        reason = result.reason.strip() or f"LLM classified as {check.category.value} ({subtype})."
        resource_categories = _SUBTYPE_RESOURCE_CATEGORIES.get(subtype, check.default_resource_categories)

        return GuardrailMatch(category=check.category, reason=reason, resource_categories=resource_categories)
