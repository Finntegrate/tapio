"""Tests for POST /chat/stream."""

import json
from unittest.mock import Mock

from fastapi.testclient import TestClient


def _parse_sse_events(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE response body into (event, data) pairs, tolerant of \\r\\n or \\n."""
    normalized = body.replace("\r\n", "\n")
    events = []
    for chunk in normalized.strip().split("\n\n"):
        raw_event = chunk.strip()
        if not raw_event:
            continue
        event_type = "message"
        data_lines = []
        for line in raw_event.splitlines():
            if line.startswith("event:"):
                event_type = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        data = json.loads("\n".join(data_lines)) if data_lines else {}
        events.append((event_type, data))
    return events


def test_chat_stream_emits_routing_citation_tokens_then_done(client: TestClient) -> None:
    response = client.post(
        "/chat/stream",
        json={"message": "How do I apply for a residence permit?", "history": [], "agent_id": "ilmarinen"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    event_types = [event_type for event_type, _ in events]

    assert event_types[0] == "routing"
    assert event_types[1] == "citation"
    assert event_types[-1] == "done"
    assert event_types.count("token") == 2  # "Mocked " + "response" from the fixture's fake stream

    routing_data = events[0][1]
    assert routing_data["agent_id"] == "ilmarinen"
    assert routing_data["was_explicit"] is True

    citation_data = events[1][1]
    assert citation_data["citations"][0]["source_url"] == "https://example.com"

    token_texts = [data["text"] for event_type, data in events if event_type == "token"]
    assert "".join(token_texts) == "Mocked response"


def test_chat_stream_auto_routes_without_explicit_agent(client: TestClient) -> None:
    response = client.post(
        "/chat/stream",
        json={"message": "Where can I find an apartment to rent?"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    routing_data = events[0][1]

    assert routing_data["agent_id"] == "otso"
    assert routing_data["was_explicit"] is False


def test_chat_stream_intercepts_crisis_adjacent_messages_before_rag(
    client: TestClient, mock_rag_orchestrator: Mock
) -> None:
    response = client.post(
        "/chat/stream",
        json={"message": "I want to kill myself, I don't know who to talk to."},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    event_types = [event_type for event_type, _ in events]

    assert event_types == ["routing", "guardrail", "citation", "token", "done"]
    mock_rag_orchestrator.query_stream.assert_not_called()

    guardrail_data = dict(events)["guardrail"]
    assert guardrail_data["category"] == "crisis"

    citation_data = dict(events)["citation"]
    assert citation_data["citations"] == []

    token_text = next(data["text"] for event_type, data in events if event_type == "token")
    assert "MIELI Crisis Helpline" in token_text


def test_chat_stream_intercepts_out_of_scope_messages_before_rag(
    client: TestClient, mock_rag_orchestrator: Mock
) -> None:
    response = client.post(
        "/chat/stream",
        json={"message": "Can you write me a poem about autumn?"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    event_types = [event_type for event_type, _ in events]

    assert event_types == ["routing", "guardrail", "citation", "token", "done"]
    mock_rag_orchestrator.query_stream.assert_not_called()

    guardrail_data = dict(events)["guardrail"]
    assert guardrail_data["category"] == "out_of_scope"


def test_chat_stream_emits_error_event_when_orchestrator_fails(client: TestClient, mock_rag_orchestrator: Mock) -> None:
    mock_rag_orchestrator.query_stream.side_effect = RuntimeError("boom")

    response = client.post(
        "/chat/stream",
        json={"message": "How do I apply for a residence permit?", "agent_id": "ilmarinen"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    event_types = [event_type for event_type, _ in events]

    assert event_types[0] == "routing"
    assert event_types[-1] == "error"
    assert "done" not in event_types

    error_data = events[-1][1]
    assert error_data["message"] == "I encountered an error while processing your query. Please try again."
