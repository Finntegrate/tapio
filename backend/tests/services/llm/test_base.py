"""Tests for the shared LLMProvider message-building helpers."""

from app.services.llm.base import build_messages


def test_build_messages_normalizes_structured_history() -> None:
    """Test structured content-block history is normalized to plain text."""
    messages = build_messages(
        prompt="What should I do next?",
        system_prompt=None,
        history=[
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Welcome"}]},
        ],
    )

    assert messages == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Welcome"},
        {"role": "user", "content": "What should I do next?"},
    ]


def test_build_messages_includes_system_prompt() -> None:
    """A system prompt, when given, becomes the first message."""
    messages = build_messages(prompt="Hi", system_prompt="You are helpful.", history=None)

    assert messages == [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
    ]


def test_build_messages_truncates_history() -> None:
    """Only the most recent MAX_HISTORY_MESSAGES turns are kept."""
    history = [{"role": "user", "content": f"message {i}"} for i in range(20)]

    messages = build_messages(prompt="latest question", system_prompt=None, history=history)

    assert messages[:-1] == history[-10:]
    assert messages[-1] == {"role": "user", "content": "latest question"}
