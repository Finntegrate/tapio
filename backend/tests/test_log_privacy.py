"""Conversation content never reaches logs or third-party tracing (#191, ADR 0011)."""

import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.log_privacy import (
    TRACING_FLAGS,
    TRACING_TARGETS,
    ThirdPartyTracingError,
    describe_exception,
    install_content_free_exception_logging,
    quiet_content_logging_libraries,
    refuse_third_party_tracing,
)

# A string no real log line would contain, standing in for something a user typed.
CANARY = "canary-4f1c-my-address-is-Mannerheimintie-1"


@pytest.mark.parametrize("flag", TRACING_FLAGS)
@pytest.mark.parametrize("value", ["true", "1", "TRUE", "yes"])
def test_refuses_to_start_with_tracing_switched_on(flag: str, value: str) -> None:
    with pytest.raises(ThirdPartyTracingError, match=flag):
        refuse_third_party_tracing({flag: value})


@pytest.mark.parametrize("target", TRACING_TARGETS)
def test_refuses_to_start_with_a_tracing_key_or_endpoint_set(target: str) -> None:
    with pytest.raises(ThirdPartyTracingError, match=target) as raised:
        refuse_third_party_tracing({target: "lsv2_secret-value"})

    assert "lsv2_secret-value" not in str(raised.value)  # names the variable, never its value


@pytest.mark.parametrize("value", ["", "false", "0", "off"])
def test_starts_with_tracing_explicitly_off(value: str) -> None:
    refuse_third_party_tracing({"LANGCHAIN_TRACING_V2": value})


def test_creating_the_app_refuses_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    with pytest.raises(ThirdPartyTracingError):
        create_app()


def _lookup() -> None:
    raise KeyError(CANARY)


def _raise_chained() -> None:
    try:
        _lookup()
    except KeyError as inner:
        msg = f"provider rejected prompt: {CANARY}"
        raise ValueError(msg) from inner


def test_describing_an_exception_keeps_its_type_and_location_but_never_its_message() -> None:
    try:
        _raise_chained()
    except ValueError as error:
        description = describe_exception(error)

    assert CANARY not in description
    assert description.startswith("ValueError at tests/test_log_privacy.py:")
    assert "in _raise_chained" in description
    assert "raised from: KeyError at" in description


def test_logged_exceptions_carry_no_message(caplog: pytest.LogCaptureFixture) -> None:
    install_content_free_exception_logging()

    with caplog.at_level(logging.DEBUG):
        try:
            _raise_chained()
        except ValueError:
            logging.getLogger("app.anything").exception("Error streaming chat turn")

    assert CANARY not in caplog.text
    assert "ValueError at" in caplog.text


def test_a_later_switch_of_the_root_to_debug_cannot_unquiet_them() -> None:
    root = logging.getLogger()
    original = root.level
    library = logging.getLogger("sse_starlette")
    library.setLevel(logging.NOTSET)
    try:
        root.setLevel(logging.WARNING)
        quiet_content_logging_libraries()
        root.setLevel(logging.DEBUG)

        assert not logging.getLogger("sse_starlette.sse").isEnabledFor(logging.DEBUG)
    finally:
        root.setLevel(original)


def test_libraries_that_log_content_are_held_at_info_even_under_debug() -> None:
    logging.getLogger("sse_starlette").setLevel(logging.DEBUG)

    quiet_content_logging_libraries()

    assert not logging.getLogger("sse_starlette.sse").isEnabledFor(logging.DEBUG)
    assert not logging.getLogger("openai").isEnabledFor(logging.DEBUG)


@pytest.fixture
def all_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Capture every logger at DEBUG, with the app's log-privacy guards in place."""
    install_content_free_exception_logging()
    quiet_content_logging_libraries()
    with caplog.at_level(logging.DEBUG):
        yield caplog


def _assert_no_canary(caplog: pytest.LogCaptureFixture) -> None:
    assert CANARY not in caplog.text
    for record in caplog.records:
        assert CANARY not in record.getMessage()
        assert CANARY not in (record.exc_text or "")


def _chat(client: TestClient, message: str) -> str:
    response = client.post("/chat/stream", json={"message": message})
    assert response.status_code == 200
    return response.text


def test_a_normal_chat_turn_logs_none_of_the_message(client: TestClient, all_logs: pytest.LogCaptureFixture) -> None:
    _chat(client, f"How do I renew my permit? {CANARY}")

    _assert_no_canary(all_logs)


def test_a_guardrailed_chat_turn_logs_none_of_the_message_or_the_models_reason(
    client: TestClient, all_logs: pytest.LogCaptureFixture
) -> None:
    with patch("app.streaming.build_guardrail_response", AsyncMock(return_value="Not something I can help with.")):
        body = _chat(client, f"Write me a poem about {CANARY}")

    assert "guardrail" in body
    _assert_no_canary(all_logs)
    assert not any("Off-topic creative writing" in r.getMessage() for r in all_logs.records)


def test_a_failing_chat_turn_logs_the_error_type_but_none_of_the_message(
    client: TestClient, mock_orchestrator_graph: Mock, all_logs: pytest.LogCaptureFixture
) -> None:
    mock_orchestrator_graph.query_stream.side_effect = RuntimeError(f"model choked on: {CANARY}")

    body = _chat(client, f"What does Kela pay? {CANARY}")

    assert "error" in body
    _assert_no_canary(all_logs)
    assert "RuntimeError at" in all_logs.text
