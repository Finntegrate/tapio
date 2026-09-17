"""Tests for building and using the configured LangChain chat model (#9)."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.config.config_models import RAGConfig
from app.config.llm_settings import LLMSettings
from app.services.chat_model import (
    build_chat_model,
    build_messages,
    check_model_availability,
    invoke_text,
    stream_text,
)


class TestBuildMessages:
    """Tests for the message-building helpers shared by every provider."""

    def test_build_messages_normalizes_structured_history(self) -> None:
        """Structured content-block history is normalized to plain text."""
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

    def test_build_messages_includes_system_prompt(self) -> None:
        """A system prompt, when given, becomes the first message."""
        messages = build_messages(prompt="Hi", system_prompt="You are helpful.", history=None)

        assert messages == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]

    def test_build_messages_truncates_history(self) -> None:
        """Only the most recent MAX_HISTORY_MESSAGES turns are kept."""
        history = [{"role": "user", "content": f"message {i}"} for i in range(20)]

        messages = build_messages(prompt="latest question", system_prompt=None, history=history)

        assert messages[:-1] == history[-10:]
        assert messages[-1] == {"role": "user", "content": "latest question"}


class TestInvokeAndStreamText:
    """Tests for the invoke/stream text-extraction wrappers."""

    def test_invoke_text_extracts_plain_string_content(self) -> None:
        model = Mock(spec=BaseChatModel)
        model.invoke.return_value = Mock(content="Plain response")

        result = invoke_text(model, [{"role": "user", "content": "Hi"}])

        assert result == "Plain response"
        model.invoke.assert_called_once_with([{"role": "user", "content": "Hi"}])

    def test_invoke_text_extracts_content_block_list(self) -> None:
        """Some providers return content as a list of blocks rather than a plain string."""
        model = Mock(spec=BaseChatModel)
        model.invoke.return_value = Mock(content=[{"type": "text", "text": "Block response"}])

        assert invoke_text(model, [{"role": "user", "content": "Hi"}]) == "Block response"

    def test_stream_text_yields_nonempty_chunks(self) -> None:
        model = Mock(spec=BaseChatModel)
        model.stream.return_value = iter([Mock(content="First "), Mock(content=""), Mock(content="second")])

        chunks = list(stream_text(model, [{"role": "user", "content": "Hi"}]))

        assert chunks == ["First ", "second"]


class TestBuildChatModel:
    """Tests for provider selection and config-to-kwarg wiring."""

    def test_builds_ollama_by_default(self) -> None:
        config = RAGConfig(llm_provider="ollama", llm_model_name="gemma4:latest", max_tokens=512)

        model = build_chat_model(config, LLMSettings())

        assert isinstance(model, ChatOllama)
        assert model.model == "gemma4:latest"
        # Ollama's field is num_predict, not max_tokens — a bare max_tokens kwarg is silently ignored.
        assert model.num_predict == 512

    def test_builds_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        config = RAGConfig(llm_provider="openai", llm_model_name="gpt-4o-mini", max_tokens=256)

        model = build_chat_model(config, LLMSettings())

        assert isinstance(model, ChatOpenAI)
        assert model.model_name == "gpt-4o-mini"
        assert model.max_tokens == 256

    def test_builds_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        config = RAGConfig(llm_provider="anthropic", llm_model_name="claude-3-5-haiku-20241022")

        model = build_chat_model(config, LLMSettings())

        assert isinstance(model, ChatAnthropic)
        assert model.model == "claude-3-5-haiku-20241022"

    def test_scaleway_style_openai_compatible_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """provider='openai' + api_base covers Scaleway and other OpenAI-compatible endpoints."""
        monkeypatch.setenv("TAPIO_LLM_API_BASE", "https://api.scaleway.ai/v1")
        monkeypatch.setenv("TAPIO_LLM_API_KEY", "secret-key")
        config = RAGConfig(llm_provider="openai", llm_model_name="llama-3.1-8b-instruct")

        model = build_chat_model(config, LLMSettings())

        assert isinstance(model, ChatOpenAI)
        assert str(model.openai_api_base) == "https://api.scaleway.ai/v1"
        assert model.openai_api_key is not None
        assert model.openai_api_key.get_secret_value() == "secret-key"

    def test_timeout_is_baked_into_the_ollama_instance(self) -> None:
        """ChatOllama has no top-level timeout field — it must go through client_kwargs."""
        config = RAGConfig(llm_provider="ollama", llm_model_name="gemma4:latest")

        model = build_chat_model(config, LLMSettings(), timeout=30.0)

        assert model.client_kwargs is not None
        assert model.client_kwargs.get("timeout") == 30.0

    def test_timeout_is_baked_into_a_cloud_provider_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        config = RAGConfig(llm_provider="openai", llm_model_name="gpt-4o-mini")

        model = build_chat_model(config, LLMSettings(), timeout=30.0)

        assert model.request_timeout == 30.0


class TestCheckModelAvailability:
    """Tests for the /health-facing availability check."""

    @patch("app.services.chat_model.ollama.list")
    def test_ollama_available_on_exact_model_match(self, mock_list) -> None:
        installed = MagicMock()
        installed.model = "gemma4:latest"
        mock_list.return_value = MagicMock(models=[installed])

        assert check_model_availability(ChatOllama(model="gemma4:latest")) is True

    @patch("app.services.chat_model.ollama.list")
    def test_ollama_unavailable_on_tag_mismatch(self, mock_list) -> None:
        """An installed variant with a different tag must not count as a match."""
        installed = MagicMock()
        installed.model = "gemma4:e4b"
        mock_list.return_value = MagicMock(models=[installed])

        assert check_model_availability(ChatOllama(model="gemma4:latest")) is False

    @patch("app.services.chat_model.ollama.list")
    def test_ollama_unavailable_when_no_models_installed(self, mock_list) -> None:
        mock_list.return_value = MagicMock(models=[])

        assert check_model_availability(ChatOllama(model="gemma4:latest")) is False

    @patch("app.services.chat_model.ollama.list")
    def test_ollama_unavailable_when_connection_fails(self, mock_list) -> None:
        mock_list.side_effect = Exception("Connection refused")

        assert check_model_availability(ChatOllama(model="gemma4:latest")) is False

    def test_openai_available_via_tapio_llm_api_key_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TAPIO_LLM_API_KEY counts even though it isn't OPENAI_API_KEY itself — this is the
        credential source build_chat_model actually uses for an explicit key (see its own
        tests), so it's the one check_model_availability needs to recognize as configured."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("TAPIO_LLM_API_KEY", "secret-key")
        model = ChatOpenAI(model="gpt-4o-mini", api_key="secret-key")

        assert check_model_availability(model) is True

    def test_openai_unavailable_with_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        model = ChatOpenAI(model="gpt-4o-mini", api_key="placeholder-not-from-env-or-settings")

        assert check_model_availability(model) is False

    def test_openai_available_via_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        model = ChatOpenAI(model="gpt-4o-mini")

        assert check_model_availability(model) is True

    def test_anthropic_unavailable_with_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        model = ChatAnthropic(model="claude-3-5-haiku-20241022")

        assert check_model_availability(model) is False

    def test_anthropic_available_via_tapio_llm_api_key_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TAPIO_LLM_API_KEY counts even though it isn't ANTHROPIC_API_KEY itself."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("TAPIO_LLM_API_KEY", "secret-key")
        model = ChatAnthropic(model="claude-3-5-haiku-20241022")

        assert check_model_availability(model) is True

    def test_unrecognized_model_type_defaults_to_available(self) -> None:
        """A model type we have no credential check for is assumed available."""
        assert check_model_availability(Mock(spec=BaseChatModel)) is True
