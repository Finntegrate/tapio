"""The baseline spec's "Language model" cases: what a registered tool can never reach (ADR 0011)."""

import pytest
from langchain_core.tools import StructuredTool, tool

from app.prompts import load_prompt
from app.tools import TOOL_SPECS, CostTier, ToolRegistry, ToolSpec
from app.tools.boundaries import FORBIDDEN_ARGUMENT_PARTS, RestrictedResource


class _FakeCheckpointStore(RestrictedResource):
    """Stands in for a store a tool must never hold."""

    def read(self, conversation: str) -> str:
        return conversation


def test_no_shipped_tool_accepts_an_identifying_argument() -> None:
    """Spec: no registered tool accepts a conversation, session, or account identifier."""
    for spec in TOOL_SPECS:
        for name in spec.tool.args:
            assert not any(part in name.lower() for part in FORBIDDEN_ARGUMENT_PARTS), (spec.name, name)


def test_every_shipped_tool_is_read_only_and_free_during_the_beta() -> None:
    assert all(spec.read_only and spec.cost_tier is CostTier.FREE for spec in TOOL_SPECS)


@pytest.mark.parametrize("argument", ["thread_id", "conversation_id", "sessionId", "account"])
def test_registration_rejects_a_tool_taking_an_identifying_argument(argument: str) -> None:
    """Spec: a prompt telling the model to read another conversation has no tool to do it with."""

    def read_conversation(**kwargs: str) -> str:
        return str(kwargs)

    leaky = StructuredTool.from_function(
        read_conversation,
        name="read_conversation",
        description="Read a conversation.",
        args_schema={"type": "object", "properties": {argument: {"type": "string"}}},
    )

    with pytest.raises(ValueError, match="identifying arguments"):
        ToolRegistry([ToolSpec(leaky, CostTier.FREE, read_only=True)])


def test_registration_rejects_a_tool_closing_over_a_restricted_store() -> None:
    store = _FakeCheckpointStore()

    @tool
    def latest_message() -> str:
        """Return the latest stored message."""
        return store.read("latest")

    with pytest.raises(ValueError, match="restricted handles"):
        ToolRegistry([ToolSpec(latest_message, CostTier.FREE, read_only=True)])


def test_registration_rejects_a_restricted_store_passed_as_a_default_argument() -> None:
    def peek(store: RestrictedResource = _FakeCheckpointStore()) -> str:  # noqa: B008
        return type(store).__name__

    peeking = StructuredTool.from_function(
        peek, name="peek", description="Peek.", args_schema={"type": "object", "properties": {}}
    )

    with pytest.raises(ValueError, match="restricted handles"):
        ToolRegistry([ToolSpec(peeking, CostTier.FREE, read_only=True)])


def test_registration_rejects_a_tool_that_is_not_read_only() -> None:
    @tool
    def delete_everything() -> str:
        """Delete everything."""
        return "deleted"

    with pytest.raises(ValueError, match="not read-only"):
        ToolRegistry([ToolSpec(delete_everything, CostTier.FREE, read_only=False)])


def test_user_question_and_reference_data_sit_in_separate_delimited_sections() -> None:
    """Delimiters keep the sections apart for the model; isolation doesn't rely on them."""
    prompt = load_prompt("user_query", context="CONTEXT", question="QUESTION")

    data_start, data_end = prompt.index("--- BEGIN REFERENCE DATA ---"), prompt.index("--- END REFERENCE DATA ---")
    question_start = prompt.index("--- BEGIN USER QUESTION ---")
    question_end = prompt.index("--- END USER QUESTION ---")
    assert data_start < prompt.index("CONTEXT") < data_end < question_start < prompt.index("QUESTION", question_start)
    assert prompt.index("QUESTION", question_start) < question_end
