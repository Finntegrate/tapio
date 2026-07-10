"""Unit tests for ConversationalTestCase models and ConversationRunner."""

from unittest.mock import Mock

import pytest

from tapio.evaluation import (
    ConversationalTestCase,
    ConversationResult,
    ConversationRunner,
    ConversationTurn,
    TurnResult,
)


class TestConversationTurn:
    """ConversationTurn data class."""

    def test_minimal_turn(self) -> None:
        turn = ConversationTurn(query="Hello")
        assert turn.query == "Hello"
        assert turn.expected_response_contains is None
        assert turn.retrieval_targets is None

    def test_full_turn(self) -> None:
        turn = ConversationTurn(
            query="How do I apply?",
            expected_response_contains=["application", "residence"],
            retrieval_targets=["https://migri.fi/en/residence"],
        )
        assert turn.query == "How do I apply?"
        assert turn.expected_response_contains == ["application", "residence"]
        assert turn.retrieval_targets == ["https://migri.fi/en/residence"]


class TestConversationalTestCase:
    """ConversationalTestCase data class."""

    def test_minimal_case(self) -> None:
        case = ConversationalTestCase(
            test_case_id="mt_001",
            turns=[ConversationTurn(query="Hello")],
        )
        assert case.test_case_id == "mt_001"
        assert len(case.turns) == 1

    def test_full_case(self) -> None:
        case = ConversationalTestCase(
            test_case_id="mt_002",
            turns=[
                ConversationTurn(query="First question"),
                ConversationTurn(query="Follow up"),
            ],
            domain_id="citizenship",
            persona_id="long_term_resident",
            description="Test multi-turn conversation",
        )
        assert case.domain_id == "citizenship"
        assert case.persona_id == "long_term_resident"
        assert len(case.turns) == 2


class TestConversationResult:
    """ConversationResult and TurnResult data classes."""

    def test_all_pass(self) -> None:
        turn = ConversationTurn(query="Hello")
        results = [
            TurnResult(turn=turn, response="Hi there", retrieved_docs=[], passed=True),
        ]
        conv_result = ConversationResult(
            test_case=ConversationalTestCase(
                test_case_id="mt_001",
                turns=[turn],
            ),
            turn_results=results,
        )
        assert conv_result.passed is True

    def test_any_fail(self) -> None:
        turn = ConversationTurn(query="Hello")
        results = [
            TurnResult(
                turn=turn,
                response="Hi",
                retrieved_docs=[],
                passed=False,
                failures=["Missing keyword"],
            ),
        ]
        conv_result = ConversationResult(
            test_case=ConversationalTestCase(
                test_case_id="mt_001",
                turns=[turn],
            ),
            turn_results=results,
        )
        assert conv_result.passed is False

    def test_summary_format(self) -> None:
        turn = ConversationTurn(query="Hello")
        results = [
            TurnResult(turn=turn, response="Hi", retrieved_docs=[], passed=True),
        ]
        conv_result = ConversationResult(
            test_case=ConversationalTestCase(
                test_case_id="mt_001",
                turns=[turn],
            ),
            turn_results=results,
        )
        summary = conv_result.summary
        assert "mt_001" in summary
        assert "PASS" in summary


class TestConversationRunner:
    """ConversationRunner with mocked RAG orchestrator."""

    @pytest.fixture
    def mock_doc(self) -> Mock:
        doc = Mock()
        doc.page_content = "Finnish residence permit information"
        doc.metadata = {"url": "https://migri.fi/en/residence"}
        return doc

    @pytest.fixture
    def mock_orchestrator(self, mock_doc: Mock) -> Mock:
        orchestrator = Mock()
        orchestrator.query.return_value = (
            "You need to apply for a residence permit through Migri.",
            [mock_doc],
        )
        return orchestrator

    def test_run_single_turn(self, mock_orchestrator: Mock) -> None:
        runner = ConversationRunner(mock_orchestrator)
        case = ConversationalTestCase(
            test_case_id="mt_001",
            turns=[ConversationTurn(query="How do I apply?")],
        )

        result = runner.run(case)

        assert result.test_case.test_case_id == "mt_001"
        assert len(result.turn_results) == 1
        assert result.turn_results[0].response == ("You need to apply for a residence permit through Migri.")
        mock_orchestrator.query.assert_called_once_with(
            query_text="How do I apply?",
            history=[],
        )

    def test_run_multi_turn(self, mock_orchestrator: Mock) -> None:
        runner = ConversationRunner(mock_orchestrator)
        case = ConversationalTestCase(
            test_case_id="mt_002",
            turns=[
                ConversationTurn(query="First question"),
                ConversationTurn(query="Follow up"),
            ],
        )

        result = runner.run(case)

        assert len(result.turn_results) == 2
        assert mock_orchestrator.query.call_count == 2

        # First call: no history
        first_call = mock_orchestrator.query.call_args_list[0]
        assert first_call[1]["query_text"] == "First question"
        assert first_call[1]["history"] == []

        # Second call: history should have first Q&A
        second_call = mock_orchestrator.query.call_args_list[1]
        assert second_call[1]["query_text"] == "Follow up"
        assert len(second_call[1]["history"]) == 2
        assert second_call[1]["history"][0] == {
            "role": "user",
            "content": "First question",
        }
        assert second_call[1]["history"][1] == {
            "role": "assistant",
            "content": "You need to apply for a residence permit through Migri.",
        }

    def test_expected_response_contains_pass(
        self,
        mock_orchestrator: Mock,
    ) -> None:
        runner = ConversationRunner(mock_orchestrator)
        case = ConversationalTestCase(
            test_case_id="mt_003",
            turns=[
                ConversationTurn(
                    query="How do I apply?",
                    expected_response_contains=["residence permit", "Migri"],
                ),
            ],
        )

        result = runner.run(case)

        assert result.passed is True

    def test_expected_response_contains_fail(
        self,
        mock_orchestrator: Mock,
    ) -> None:
        runner = ConversationRunner(mock_orchestrator)
        case = ConversationalTestCase(
            test_case_id="mt_004",
            turns=[
                ConversationTurn(
                    query="How do I apply?",
                    expected_response_contains=["nonexistent_keyword_xyz"],
                ),
            ],
        )

        result = runner.run(case)

        assert result.passed is False
        assert len(result.turn_results[0].failures) == 1
        assert "nonexistent_keyword_xyz" in result.turn_results[0].failures[0]

    def test_retrieval_targets_pass(
        self,
        mock_orchestrator: Mock,
        mock_doc: Mock,
    ) -> None:
        runner = ConversationRunner(mock_orchestrator)
        case = ConversationalTestCase(
            test_case_id="mt_005",
            turns=[
                ConversationTurn(
                    query="How do I apply?",
                    retrieval_targets=["https://migri.fi/en/residence"],
                ),
            ],
        )

        result = runner.run(case)

        assert result.passed is True

    def test_retrieval_targets_fail(
        self,
        mock_orchestrator: Mock,
        mock_doc: Mock,
    ) -> None:
        runner = ConversationRunner(mock_orchestrator)
        case = ConversationalTestCase(
            test_case_id="mt_006",
            turns=[
                ConversationTurn(
                    query="How do I apply?",
                    retrieval_targets=["https://example.com/missing"],
                ),
            ],
        )

        result = runner.run(case)

        assert result.passed is False
        assert len(result.turn_results[0].failures) == 1
        assert "example.com" in result.turn_results[0].failures[0]
