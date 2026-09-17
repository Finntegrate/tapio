"""Tests for the LiteLLM-backed LLMProvider implementation."""

from unittest.mock import MagicMock, patch

from app.services.llm.litellm_provider import LiteLLMProvider


def _completion_response(content: str) -> MagicMock:
    """Build a mock litellm.completion() non-streaming return value."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


def _stream_chunk(content: str | None) -> MagicMock:
    """Build a mock litellm.completion(stream=True) chunk."""
    chunk = MagicMock()
    chunk.choices = [MagicMock(delta=MagicMock(content=content))]
    return chunk


class TestLiteLLMProvider:
    """Tests for the LiteLLMProvider class."""

    def test_init_defaults(self):
        """Test LiteLLMProvider initialization with default parameters."""
        provider = LiteLLMProvider("openai/gpt-4o-mini")

        assert provider.model_name == "openai/gpt-4o-mini"
        assert provider.max_tokens == 1024
        assert provider.temperature == 0.7
        assert provider.api_base is None
        assert provider.api_key is None

    def test_init_with_custom_parameters(self):
        """Test LiteLLMProvider initialization with Scaleway-style custom parameters."""
        provider = LiteLLMProvider(
            model_name="openai/llama-3.1-8b-instruct",
            max_tokens=2048,
            temperature=0.5,
            api_base="https://api.scaleway.ai/v1",
            api_key="secret-key",
        )

        assert provider.model_name == "openai/llama-3.1-8b-instruct"
        assert provider.max_tokens == 2048
        assert provider.temperature == 0.5
        assert provider.api_base == "https://api.scaleway.ai/v1"
        assert provider.api_key == "secret-key"

    def test_get_model_name(self):
        """Test getting the model name."""
        provider = LiteLLMProvider("anthropic/claude-3-5-haiku-20241022")
        assert provider.get_model_name() == "anthropic/claude-3-5-haiku-20241022"

    def test_check_model_availability_with_explicit_api_key(self):
        """An explicit api_key is trusted without consulting the environment."""
        provider = LiteLLMProvider("openai/gpt-4o-mini", api_key="secret-key")

        with patch("app.services.llm.litellm_provider.litellm.validate_environment") as mock_validate:
            assert provider.check_model_availability() is True
        mock_validate.assert_not_called()

    @patch("app.services.llm.litellm_provider.litellm.validate_environment")
    def test_check_model_availability_env_configured(self, mock_validate):
        """Environment-provided credentials are detected via LiteLLM's own check."""
        mock_validate.return_value = {"keys_in_environment": True, "missing_keys": []}

        provider = LiteLLMProvider("openai/gpt-4o-mini")
        result = provider.check_model_availability()

        assert result is True
        mock_validate.assert_called_once_with("openai/gpt-4o-mini")

    @patch("app.services.llm.litellm_provider.litellm.validate_environment")
    def test_check_model_availability_missing_keys(self, mock_validate, caplog):
        """Missing provider credentials are reported as unavailable."""
        import logging

        caplog.set_level(logging.WARNING, logger="app.services.llm.litellm_provider")
        mock_validate.return_value = {"keys_in_environment": False, "missing_keys": ["ANTHROPIC_API_KEY"]}

        provider = LiteLLMProvider("anthropic/claude-3-5-haiku-20241022")
        result = provider.check_model_availability()

        assert result is False
        assert "ANTHROPIC_API_KEY" in caplog.text

    @patch("app.services.llm.litellm_provider.litellm.validate_environment")
    def test_check_model_availability_handles_validation_error(self, mock_validate):
        """A failure inside LiteLLM's own validation is treated as unavailable, not raised."""
        mock_validate.side_effect = Exception("boom")

        provider = LiteLLMProvider("openai/gpt-4o-mini")
        result = provider.check_model_availability()

        assert result is False

    @patch("app.services.llm.litellm_provider.litellm.completion")
    def test_generate_response_success(self, mock_completion):
        """Test successful response generation."""
        mock_completion.return_value = _completion_response("This is a test response.")

        provider = LiteLLMProvider("openai/gpt-4o-mini", max_tokens=512, temperature=0.5)
        result = provider.generate_response("Test prompt")

        assert result == "This is a test response."
        mock_completion.assert_called_once_with(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": "Test prompt"}],
            max_tokens=512,
            temperature=0.5,
            api_base=None,
            api_key=None,
            timeout=None,
        )

    @patch("app.services.llm.litellm_provider.litellm.completion")
    def test_generate_response_with_system_prompt_and_history(self, mock_completion):
        """Test response generation includes system prompt and prior turns."""
        mock_completion.return_value = _completion_response("Sure, following up.")

        provider = LiteLLMProvider("openai/gpt-4o-mini")
        result = provider.generate_response(
            prompt="How do I apply for one?",
            system_prompt="You are a helpful assistant.",
            history=[{"role": "user", "content": "What is a residence permit?"}],
        )

        assert result == "Sure, following up."
        sent_messages = mock_completion.call_args.kwargs["messages"]
        assert sent_messages == [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is a residence permit?"},
            {"role": "user", "content": "How do I apply for one?"},
        ]

    @patch("app.services.llm.litellm_provider.litellm.completion")
    def test_generate_response_passes_scaleway_style_config(self, mock_completion):
        """api_base and api_key reach the LiteLLM call, e.g. for a Scaleway endpoint."""
        mock_completion.return_value = _completion_response("ok")

        provider = LiteLLMProvider(
            "openai/llama-3.1-8b-instruct",
            api_base="https://api.scaleway.ai/v1",
            api_key="secret-key",
        )
        provider.generate_response("Test prompt", timeout=5.0)

        mock_completion.assert_called_once_with(
            model="openai/llama-3.1-8b-instruct",
            messages=[{"role": "user", "content": "Test prompt"}],
            max_tokens=1024,
            temperature=0.7,
            api_base="https://api.scaleway.ai/v1",
            api_key="secret-key",
            timeout=5.0,
        )

    @patch("app.services.llm.litellm_provider.litellm.completion")
    def test_generate_response_error(self, mock_completion):
        """Test response generation when the provider call fails."""
        mock_completion.side_effect = Exception("Connection error")

        provider = LiteLLMProvider("openai/gpt-4o-mini")
        result = provider.generate_response("Test prompt")

        assert "Error: Could not generate a response" in result
        assert "openai/gpt-4o-mini" in result

    @patch("app.services.llm.litellm_provider.litellm.completion")
    def test_generate_response_stream_yields_content(self, mock_completion):
        """Test streamed chunks are yielded as they arrive."""
        mock_completion.return_value = [_stream_chunk("First "), _stream_chunk("second")]

        chunks = list(LiteLLMProvider("openai/gpt-4o-mini").generate_response_stream("Test prompt"))

        assert chunks == ["First ", "second"]
        assert mock_completion.call_args.kwargs["stream"] is True

    @patch("app.services.llm.litellm_provider.litellm.completion")
    def test_generate_response_stream_skips_empty_deltas(self, mock_completion):
        """A chunk with no delta content (e.g. a role-only chunk) yields nothing."""
        mock_completion.return_value = [_stream_chunk(None), _stream_chunk("content")]

        chunks = list(LiteLLMProvider("openai/gpt-4o-mini").generate_response_stream("Test prompt"))

        assert chunks == ["content"]

    @patch("app.services.llm.litellm_provider.litellm.completion")
    def test_generate_response_stream_yields_a_safe_error_message(self, mock_completion):
        """A failed streaming call yields one safe error chunk instead of raising."""
        mock_completion.side_effect = Exception("Connection error")

        chunks = list(LiteLLMProvider("openai/gpt-4o-mini").generate_response_stream("Test prompt"))

        assert len(chunks) == 1
        assert "Error: Could not generate a response" in chunks[0]
