"""Conversational test case models for multi-turn evaluation."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationTurn:
    """A single turn in a multi-turn conversation test.

    Attributes:
        query: The user's query at this turn.
        expected_response_contains: Keywords the response must contain (optional).
        retrieval_targets: Expected source URLs that should appear in retrieved docs (optional).
    """

    query: str
    expected_response_contains: list[str] | None = None
    retrieval_targets: list[str] | None = None


@dataclass
class ConversationalTestCase:
    """A multi-turn conversation test case.

    Each case defines a sequence of turns that build on prior conversation
    history, simulating a real user session.

    Attributes:
        test_case_id: Unique identifier for the test case.
        turns: Ordered list of conversation turns.
        domain_id: The domain this case belongs to (e.g. residence_permit).
        persona_id: Optional persona identifier (e.g. long_term_resident).
        description: Human-readable description of the test scenario.
    """

    test_case_id: str
    turns: list[ConversationTurn]
    domain_id: str | None = None
    persona_id: str | None = None
    description: str | None = None


@dataclass
class TurnResult:
    """Outcome of a single conversation turn."""

    turn: ConversationTurn
    response: str
    retrieved_docs: list[Any]
    passed: bool = False
    failures: list[str] = field(default_factory=list)


@dataclass
class ConversationResult:
    """Aggregate outcome of a multi-turn conversation test."""

    test_case: ConversationalTestCase
    turn_results: list[TurnResult]

    @property
    def passed(self) -> bool:
        """True when every turn passed."""
        return all(tr.passed for tr in self.turn_results)

    @property
    def summary(self) -> str:
        """Human-readable pass/fail summary across all turns."""
        lines: list[str] = [f"Test case: {self.test_case.test_case_id}"]
        for i, tr in enumerate(self.turn_results, 1):
            status = "PASS" if tr.passed else "FAIL"
            lines.append(f"  Turn {i}: {status}")
            lines.extend(f"    - {f}" for f in tr.failures)
        return "\n".join(lines)


class ConversationRunner:
    """Runs a multi-turn conversation against a RAG orchestrator.

    Accumulates conversation history across turns so each turn can build
    on prior context, simulating a real user session.
    """

    def __init__(self, rag_orchestrator: Any) -> None:
        """Initialize runner with a RAG orchestrator."""
        self.rag_orchestrator = rag_orchestrator

    def run(self, test_case: ConversationalTestCase) -> ConversationResult:
        """Execute all turns of a conversational test case in order.

        Args:
            test_case: The multi-turn conversation to run.

        Returns:
            A ConversationResult with per-turn outcomes.
        """
        history: list[dict[str, Any]] = []
        turn_results: list[TurnResult] = []

        for turn in test_case.turns:
            response, docs = self.rag_orchestrator.query(
                query_text=turn.query,
                history=list(history),
            )
            response_text = str(response)

            history.append({"role": "user", "content": turn.query})
            history.append({"role": "assistant", "content": response_text})

            result = TurnResult(
                turn=turn,
                response=response_text,
                retrieved_docs=docs,
            )

            if turn.expected_response_contains:
                response_lower = response_text.lower()
                missing = [kw for kw in turn.expected_response_contains if kw.lower() not in response_lower]
                if missing:
                    result.failures.append(
                        f"Response missing expected keywords: {missing}",
                    )

            if turn.retrieval_targets:
                retrieved_urls = {d.metadata.get("url", "") for d in docs if hasattr(d, "metadata")}
                missing_urls = [url for url in turn.retrieval_targets if url not in retrieved_urls]
                if missing_urls:
                    result.failures.append(
                        f"Missing expected retrieval targets: {missing_urls}",
                    )

            result.passed = len(result.failures) == 0
            turn_results.append(result)

        return ConversationResult(
            test_case=test_case,
            turn_results=turn_results,
        )
