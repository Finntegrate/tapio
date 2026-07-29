"""Evaluation framework models for Tapio.

Provides data models and runners for single-turn and multi-turn
conversation evaluation.
"""

from tapio.evaluation.conversational_test_case import (
    ConversationalTestCase,
    ConversationResult,
    ConversationRunner,
    ConversationTurn,
    TurnResult,
)

__all__ = [
    "ConversationResult",
    "ConversationRunner",
    "ConversationTurn",
    "ConversationalTestCase",
    "TurnResult",
]
