"""Keyword-based input classifier for guardrailed queries (#29).

Runs before agent routing and flags messages that need special handling
instead of an ordinary RAG answer: crisis-adjacent, legally sensitive, or
clearly out-of-scope (PRD §7.4). Mirrors ``AgentRouter``'s explainable,
keyword-based approach so a guardrail decision is auditable without an
extra LLM call. If/when the app moves onto a LangGraph graph, this class is
meant to become the input classifier node that runs before the routing node.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


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


@dataclass(frozen=True, slots=True)
class _Trigger:
    """One phrase group that maps to a guardrail category and resource set."""

    reason: str
    terms: tuple[str, ...]
    resource_categories: tuple[str, ...] = ()


# Ordered most life-threatening first: the first matching trigger wins, and a
# message that mentions both a crisis and, say, a permit still surfaces crisis
# support first (PRD §7.4).
_CRISIS_TRIGGERS: Final[tuple[_Trigger, ...]] = (
    _Trigger(
        reason="Message suggests an immediate risk to life or safety.",
        terms=(
            "suicide",
            "suicidal",
            "kill myself",
            "end my life",
            "want to die",
            "self-harm",
            "self harm",
            "hurt myself",
            "harm myself",
        ),
        resource_categories=("mental_health_crisis", "emergency"),
    ),
    _Trigger(
        reason="Message describes domestic violence or an abusive relationship.",
        terms=(
            "domestic violence",
            "domestic abuse",
            "being abused",
            "abusive relationship",
            "hits me",
            "beats me",
            "afraid of my partner",
            "afraid of my husband",
            "afraid of my wife",
        ),
        resource_categories=("domestic_abuse_support", "emergency"),
    ),
    _Trigger(
        reason="Message describes being the victim of a crime such as assault or trafficking.",
        terms=(
            "sexually assaulted",
            "was raped",
            "being trafficked",
            "human trafficking",
            "was assaulted",
        ),
        resource_categories=("crime_victim_support", "emergency"),
    ),
    _Trigger(
        reason="Message describes an emergency requiring immediate help.",
        terms=(
            "in immediate danger",
            "someone is hurting me",
            "call an ambulance",
            "medical emergency",
        ),
        resource_categories=("emergency",),
    ),
)

_LEGAL_SENSITIVE_TRIGGERS: Final[tuple[_Trigger, ...]] = (
    _Trigger(
        reason="Message concerns asylum, deportation, or detention.",
        terms=(
            "asylum",
            "deportation",
            "deport me",
            "being deported",
            "detention centre",
            "detention center",
            "detained by",
            "denied asylum",
            "removed from finland",
            "appeal my decision",
            "negative decision",
            "removal order",
        ),
        resource_categories=("legal_aid", "immigration_authority"),
    ),
)

_OUT_OF_SCOPE_TRIGGERS: Final[tuple[_Trigger, ...]] = (
    _Trigger(
        reason="Message asks for general-purpose help unrelated to settling in Finland.",
        terms=(
            "write me a poem",
            "write a song",
            "write me code",
            "python script",
            "tell me a joke",
            "recipe for",
            "who won the",
            "stock price",
            "solve for x",
            "homework help",
            "translate this sentence",
        ),
    ),
)

_TRIGGER_GROUPS: Final[tuple[tuple[GuardrailCategory, tuple[_Trigger, ...]], ...]] = (
    (GuardrailCategory.CRISIS, _CRISIS_TRIGGERS),
    (GuardrailCategory.LEGAL_SENSITIVE, _LEGAL_SENSITIVE_TRIGGERS),
    (GuardrailCategory.OUT_OF_SCOPE, _OUT_OF_SCOPE_TRIGGERS),
)


class GuardrailClassifier:
    """Classify a message as crisis, legally sensitive, out-of-scope, or none of those.

    This is a narrow, best-effort layer: it catches clearly crisis-adjacent,
    legally sensitive, or off-topic phrasing, but it is not a substitute for
    the RAG pipeline's own "no reliable source" honesty (PRD §7.3) for
    messages it does not flag.
    """

    def classify(self, message: str) -> GuardrailMatch | None:
        """Classify a message, checking crisis first, then legal, then off-topic.

        Args:
            message: The user's raw message.

        Returns:
            A ``GuardrailMatch`` describing the first trigger that matched, or
            ``None`` if the message needs no special handling.
        """
        normalized_message = message.casefold()
        for category, triggers in _TRIGGER_GROUPS:
            for trigger in triggers:
                if self._matches(trigger, normalized_message):
                    return GuardrailMatch(
                        category=category,
                        reason=trigger.reason,
                        resource_categories=trigger.resource_categories,
                    )
        return None

    @staticmethod
    def _matches(trigger: _Trigger, normalized_message: str) -> bool:
        """Check whether any of a trigger's phrases appear as standalone text.

        Args:
            trigger: Phrase group to test.
            normalized_message: Case-normalized user message.

        Returns:
            True if any phrase matches as a standalone word or phrase.
        """
        return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized_message) for term in trigger.terms)
