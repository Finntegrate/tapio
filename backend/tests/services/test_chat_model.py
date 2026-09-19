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


class TestRejectCleartextTransport:
    """Tests for the CWE-319 guard against sending prompts/credentials over plain HTTP."""

    def test_rejects_non_loopback_http_with_explicit_key(self) -> None:
        config = RAGConfig(llm_provider="openai", llm_model_name="llama-3.1-8b-instruct")
        llm_settings = LLMSettings(api_base="http://api.scaleway.ai/v1", api_key="secret-key")

        with pytest.raises(ValueError, match="cleartext"):
            build_chat_model(config, llm_settings)

    def test_rejects_non_loopback_http_for_a_cloud_provider_even_without_explicit_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A cloud provider always sends some credential (its own env var, if not an explicit one)."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        config = RAGConfig(llm_provider="openai", llm_model_name="gpt-4o-mini")
        llm_settings = LLMSettings(api_base="http://example.com/v1")

        with pytest.raises(ValueError, match="cleartext"):
            build_chat_model(config, llm_settings)

    def test_rejects_non_loopback_http_for_ollama_with_explicit_key(self) -> None:
        config = RAGConfig(llm_provider="ollama", llm_model_name="gemma4:latest")
        llm_settings = LLMSettings(api_base="http://192.168.1.5:11434", api_key="secret-key")

        with pytest.raises(ValueError, match="cleartext"):
            build_chat_model(config, llm_settings)

    def test_rejects_non_loopback_ollama_even_without_credentials(self) -> None:
        """Prompts and responses are sensitive even when no credential is in play."""
        config = RAGConfig(llm_provider="ollama", llm_model_name="gemma4:latest")
        llm_settings = LLMSettings(api_base="http://192.168.1.5:11434")

        with pytest.raises(ValueError, match="cleartext"):
            build_chat_model(config, llm_settings)

    def test_allows_loopback_http_for_ollama(self) -> None:
        """The default local Ollama setup must keep working."""
        config = RAGConfig(llm_provider="ollama", llm_model_name="gemma4:latest")
        llm_settings = LLMSettings(api_base="http://localhost:11434")

        model = build_chat_model(config, llm_settings)

        assert model.base_url == "http://localhost:11434"

    def test_allows_https_non_loopback_with_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        config = RAGConfig(llm_provider="openai", llm_model_name="gpt-4o-mini")
        llm_settings = LLMSettings(api_base="https://api.scaleway.ai/v1")

        model = build_chat_model(config, llm_settings)

        assert str(model.openai_api_base) == "https://api.scaleway.ai/v1"

    def test_allows_no_api_base_at_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        config = RAGConfig(llm_provider="openai", llm_model_name="gpt-4o-mini")

        build_chat_model(config, LLMSettings())  # must not raise

    @pytest.mark.parametrize(
        ("provider", "env_var"),
        [
            ("openai", "OPENAI_API_BASE"),
            ("openai", "OPENAI_BASE_URL"),
            ("anthropic", "ANTHROPIC_API_URL"),
            ("anthropic", "ANTHROPIC_BASE_URL"),
            ("ollama", "OLLAMA_HOST"),
        ],
    )
    def test_rejects_a_non_loopback_http_provider_fallback_env_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider: str,
        env_var: str,
    ) -> None:
        """TAPIO_LLM_API_BASE unset is not enough — each provider's own SDK falls back to
        its own env var, which must be checked too or the guard is trivially bypassable."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv(env_var, "http://example.com")
        config = RAGConfig(llm_provider=provider, llm_model_name="some-model")

        with pytest.raises(ValueError, match="cleartext"):
            build_chat_model(config, LLMSettings())

    def test_explicit_api_base_wins_over_a_provider_fallback_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit TAPIO_LLM_API_BASE is what's actually used, so it's what gets checked,
        even if a provider-native env var (here, an unrelated https:// one) is also set."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_API_BASE", "https://irrelevant.example.com")
        config = RAGConfig(llm_provider="openai", llm_model_name="gpt-4o-mini")
        llm_settings = LLMSettings(api_base="http://192.0.2.1/v1")

        with pytest.raises(ValueError, match="cleartext"):
            build_chat_model(config, llm_settings)


class TestCheckModelAvailability:
    """Tests for the /health-facing availability check."""

    @patch("app.services.chat_model.ollama.Client")
    def test_ollama_available_on_exact_model_match(self, mock_client_class) -> None:
        installed = MagicMock()
        installed.model = "gemma4:latest"
        mock_client_class.return_value.list.return_value = MagicMock(models=[installed])

        assert check_model_availability(ChatOllama(model="gemma4:latest")) is True

    @patch("app.services.chat_model.ollama.Client")
    def test_ollama_unavailable_on_tag_mismatch(self, mock_client_class) -> None:
        """An installed variant with a different tag must not count as a match."""
        installed = MagicMock()
        installed.model = "gemma4:e4b"
        mock_client_class.return_value.list.return_value = MagicMock(models=[installed])

        assert check_model_availability(ChatOllama(model="gemma4:latest")) is False

    @patch("app.services.chat_model.ollama.Client")
    def test_ollama_unavailable_when_no_models_installed(self, mock_client_class) -> None:
        mock_client_class.return_value.list.return_value = MagicMock(models=[])

        assert check_model_availability(ChatOllama(model="gemma4:latest")) is False

    @patch("app.services.chat_model.ollama.Client")
    def test_ollama_unavailable_when_connection_fails(self, mock_client_class) -> None:
        mock_client_class.return_value.list.side_effect = Exception("Connection refused")

        assert check_model_availability(ChatOllama(model="gemma4:latest")) is False

    @patch("app.services.chat_model.ollama.Client")
    def test_ollama_availability_queries_the_configured_remote_server(self, mock_client_class) -> None:
        """A remote TAPIO_LLM_API_BASE must be checked, not the OLLAMA_HOST/localhost default."""
        installed = MagicMock()
        installed.model = "gemma4:latest"
        mock_client_class.return_value.list.return_value = MagicMock(models=[installed])

        model = ChatOllama(model="gemma4:latest", base_url="http://ollama.internal:11434")
        assert check_model_availability(model) is True

        mock_client_class.assert_called_once_with(host="http://ollama.internal:11434")

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
        monkeypatch.delenv("TAPIO_LLM_API_KEY", raising=False)
        model = ChatOpenAI(model="gpt-4o-mini", api_key="placeholder-not-from-env-or-settings")

        assert check_model_availability(model) is False

    def test_openai_available_via_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        model = ChatOpenAI(model="gpt-4o-mini")

        assert check_model_availability(model) is True

    def test_anthropic_unavailable_with_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("TAPIO_LLM_API_KEY", raising=False)
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
