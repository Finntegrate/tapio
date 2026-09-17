"""Shared types for the guardrail classification pipeline (#29).

See ``app.guardrails.llm_classifier`` for the classifier itself: three
parallel, example-guided LLM checks (crisis, legal-sensitive, out-of-scope)
that run before agent routing, replacing what was previously a fixed
keyword/regex list. A hardcoded phrase list is brittle and English-only and
doesn't scale to the range of phrasing real users need to see recognized;
the same illustrative phrases instead ground the LLM's judgment as few-shot
examples in the classification prompt, which generalizes to phrasing and
languages the examples don't literally contain.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class GuardrailCategory(StrEnum):
    """Categories of query that need handling other than a normal RAG answer."""

    CRISIS = "crisis"
    LEGAL_SENSITIVE = "legal_sensitive"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True, slots=True)
class GuardrailMatch:
    """A classifier decision: what was matched, why, and which resources apply."""

    category: GuardrailCategory
    reason: str
    resource_categories: tuple[str, ...] = ()


@runtime_checkable
class GuardrailClassifierProtocol(Protocol):
    """What ``stream_chat_turn`` needs from the guardrail classifier."""

    async def classify(self, message: str) -> GuardrailMatch | None:
        """Classify a message for guardrail handling.

        Args:
            message: The user's raw message.

        Returns:
            A ``GuardrailMatch`` describing the category to handle specially, or ``None``
            if the message needs no special handling and should proceed to routing/RAG.
        """
        ...
