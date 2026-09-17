"""LLM-based input classifier for guardrailed queries (#29).

Runs three independent, narrowly-scoped classification checks — crisis,
legal-sensitive, out-of-scope — concurrently against the same Ollama model
the RAG pipeline uses. Each check is a focused yes/no question grounded
with a handful of few-shot examples, rather than a fixed keyword/regex
list: a hardcoded phrase list is brittle, English-only, and doesn't scale
to real phrasing, so the same illustrative phrases are given to the model
as examples instead, which generalizes to wording and languages the
examples don't literally contain.

Each check binds a Pydantic schema via LangChain's structured-output
support (``ChatOllama.with_structured_output``, Ollama's JSON-schema mode)
rather than asking for free-text JSON and parsing it by hand — the model
call itself is constrained to the schema, and a failure to produce a valid
instance raises instead of silently returning malformed text to parse.

This is the shape a LangGraph input-classifier node is expected to take
once the app's graph migration lands: parallel branches feeding one
decision, run before the routing node.

Classification is inherently less deterministic than a regex match. It
fails open (returns ``None``, letting the turn proceed to a normal RAG
answer) whenever a check's model call errors or can't satisfy the schema —
the same degradation the RAG pipeline already has for an unreachable
model, not a new failure mode.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Final

from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from app.guardrails.classifier import GuardrailCategory, GuardrailMatch
from app.prompts import load_prompt

logger = logging.getLogger(__name__)


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

# A stalled Ollama call must not leave a chat SSE stream open with no terminal event.
# Local CPU inference in manual testing took up to ~45s for a single check, so this is
# generous rather than tight; tune per deployment/model if it proves wrong either way.
_CHECK_TIMEOUT_SECONDS: Final[float] = 60.0


class LLMGuardrailClassifier:
    """Classify a message with three parallel, example-guided, structured-output LLM checks."""

    def __init__(self, model_name: str) -> None:
        """Build the structured-output-bound chat model used for classification calls.

        Args:
            model_name: The Ollama model name — shared with the RAG pipeline's LLM service
                so classification and answer generation use the same configured model.
        """
        self.model_name = model_name
        self._structured_model = ChatOllama(model=model_name).with_structured_output(GuardrailCheckResult)

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
        """Run one focused, structured-output classification check.

        Args:
            check: The category-specific check to run.
            message: The user's raw message.

        Returns:
            A ``GuardrailMatch`` if the check matched, else ``None`` (including on any
            model or parsing failure, which fails open rather than propagating).
        """
        prompt = load_prompt(
            "guardrail_check",
            criteria_description=check.criteria_description,
            subtype_options=check.subtype_options,
            examples=check.render_examples(),
            message=message,
        )
        try:
            async with asyncio.timeout(_CHECK_TIMEOUT_SECONDS):
                result = await self._structured_model.ainvoke(prompt)
        except Exception:
            logger.warning("Guardrail check %s failed to produce structured output; failing open.", check.category)
            return None

        if not isinstance(result, GuardrailCheckResult) or not result.match:
            return None

        subtype = result.subtype.strip().lower()
        reason = result.reason.strip() or f"LLM classified as {check.category.value} ({subtype})."
        resource_categories = _SUBTYPE_RESOURCE_CATEGORIES.get(subtype, check.default_resource_categories)

        return GuardrailMatch(category=check.category, reason=reason, resource_categories=resource_categories)
