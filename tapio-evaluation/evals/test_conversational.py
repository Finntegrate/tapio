"""Evaluate multi-turn conversation quality.

Runs full multi-turn conversations from the conversational dataset(s),
asserting that each turn meets keyword-based expectations.

Uses the ConversationRunner to accumulate history across turns, simulating
a real user session.
"""

import logging

import pytest

from tapio.evaluation import ConversationalTestCase, ConversationRunner, ConversationTurn

logger = logging.getLogger(__name__)


@pytest.mark.conversational
def test_conversational_multi_turn(
    multi_turn_case: tuple[str, dict],
    conversation_runner: ConversationRunner,
) -> None:
    """Run a multi-turn conversation and validate each turn's expectations."""
    _dataset_name, test_data = multi_turn_case

    test_case = ConversationalTestCase(
        test_case_id=test_data["test_case_id"],
        turns=[
            ConversationTurn(
                query=t["query"],
                expected_response_contains=t.get("expected_response_contains"),
                retrieval_targets=t.get("retrieval_targets"),
            )
            for t in test_data["turns"]
        ],
        domain_id=test_data.get("domain_id"),
        description=test_data.get("description"),
    )

    result = conversation_runner.run(test_case)

    # Log summary for debugging
    logger.info("Conversation result:\n%s", result.summary)

    assert result.passed, f"Multi-turn test case '{test_data['test_case_id']}' failed:\n{result.summary}"
