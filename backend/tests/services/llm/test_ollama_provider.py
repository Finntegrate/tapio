"""Tests for the Ollama LLMProvider implementation."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.llm.ollama_provider import OllamaProvider


class TestOllamaProvider:
    """Tests for the OllamaProvider class."""

    def test_init(self):
        """Test OllamaProvider initialization with default parameters."""
        provider = OllamaProvider()

        assert provider.model_name == "gemma4:latest"
        assert provider.max_tokens == 1024
        assert provider.temperature == 0.7

    def test_init_with_custom_parameters(self):
        """Test OllamaProvider initialization with custom parameters."""
        provider = OllamaProvider(
            model_name="llama3.2:latest",
            max_tokens=2048,
            temperature=0.5,
        )

        assert provider.model_name == "llama3.2:latest"
        assert provider.max_tokens == 2048
        assert provider.temperature == 0.5

    def test_get_model_name(self):
        """Test getting the model name."""
        provider = OllamaProvider(model_name="test-model")
        assert provider.get_model_name() == "test-model"

    @patch("app.services.llm.ollama_provider.ollama.list")
    def test_check_model_availability_no_models(self, mock_list):
        """Test model availability check when no models are available."""
        # Mock empty response
        mock_response = MagicMock()
        mock_response.models = []
        mock_list.return_value = mock_response

        provider = OllamaProvider("llama3.2")
        result = provider.check_model_availability()

        assert result is False
        mock_list.assert_called_once()

    @patch("app.services.llm.ollama_provider.ollama.list")
    def test_check_model_availability_ollama_not_running(self, mock_list):
        """Test model availability check when Ollama is not running."""
        # Mock connection error
        mock_list.side_effect = Exception("Connection refused")

        provider = OllamaProvider("llama3.2")
        result = provider.check_model_availability()

        assert result is False
        mock_list.assert_called_once()

    @pytest.mark.parametrize(
        ("requested_model", "available_models", "expected_result", "expected_log_message"),
        [
            # Exact matches
            (
                "llama3.2:latest",
                ["llama3.2:latest", "all-minilm:22m"],
                True,
                "Found exact matching model: llama3.2:latest",
            ),
            (
                "all-minilm:22m",
                ["llama3.2:latest", "all-minilm:22m"],
                True,
                "Found exact matching model: all-minilm:22m",
            ),
            # No matches
            (
                "nonexistent-model",
                ["llama3.2:latest", "all-minilm:22m"],
                False,
                "nonexistent-model model not found in Ollama",
            ),
            (
                "mistral:7b",
                ["llama3.2:latest", "all-minilm:22m"],
                False,
                "mistral:7b model not found in Ollama",
            ),
        ],
    )
    @patch("app.services.llm.ollama_provider.ollama.list")
    def test_check_model_availability_parameterized(
        self,
        mock_list,
        caplog,
        requested_model,
        available_models,
        expected_result,
        expected_log_message,
    ):
        """Test model availability check with various model name combinations."""
        # Configure logging for the test
        import logging

        caplog.set_level(logging.INFO, logger="app.services.llm.ollama_provider")

        # Create mock model objects
        mock_models = []
        for model_name in available_models:
            mock_model = MagicMock()
            mock_model.model = model_name
            mock_models.append(mock_model)

        # Mock the response
        mock_response = MagicMock()
        mock_response.models = mock_models
        mock_list.return_value = mock_response

        provider = OllamaProvider(requested_model)
        result = provider.check_model_availability()

        assert result is expected_result
        mock_list.assert_called_once()

        # Check that the expected log message appears
        assert expected_log_message in caplog.text

    @patch("app.services.llm.ollama_provider.ollama.list")
    def test_check_model_availability_requires_exact_model_tag(self, mock_list) -> None:
        """Reject an installed variant when its tag differs from the requested model."""
        installed_model = MagicMock()
        installed_model.model = "gemma4:e4b"
        mock_response = MagicMock()
        mock_response.models = [installed_model]
        mock_list.return_value = mock_response

        assert OllamaProvider("gemma4:latest").check_model_availability() is False

    @patch("app.services.llm.ollama_provider.ollama.list")
    def test_check_model_availability_logs_available_models(self, mock_list, caplog):
        """Test that available models are logged correctly."""
        # Configure logging for the test
        import logging

        caplog.set_level(logging.INFO, logger="app.services.llm.ollama_provider")

        # Create mock model objects
        mock_models = []
        model_names = ["llama3.2:latest", "all-minilm:22m", "codellama:7b"]
        for model_name in model_names:
            mock_model = MagicMock()
            mock_model.model = model_name
            mock_models.append(mock_model)

        # Mock the response
        mock_response = MagicMock()
        mock_response.models = mock_models
        mock_list.return_value = mock_response

        provider = OllamaProvider("llama3.2:latest")
        provider.check_model_availability()

        # Check that all available models are logged
        expected_log = "Available Ollama models: llama3.2:latest, all-minilm:22m, codellama:7b"
        assert expected_log in caplog.text

    @patch("app.services.llm.ollama_provider.ollama.list")
    def test_check_model_availability_handles_none_model_names(self, mock_list):
        """Test that the provider handles model objects with None names gracefully."""
        # Create mock model objects with some None names
        mock_models = []

        # Valid model
        valid_model = MagicMock()
        valid_model.model = "llama3.2:latest"
        mock_models.append(valid_model)

        # Model with None name (should be filtered out)
        none_model = MagicMock()
        none_model.model = None
        mock_models.append(none_model)

        # Another valid model
        valid_model2 = MagicMock()
        valid_model2.model = "all-minilm:22m"
        mock_models.append(valid_model2)

        # Mock the response
        mock_response = MagicMock()
        mock_response.models = mock_models
        mock_list.return_value = mock_response

        provider = OllamaProvider("llama3.2:latest")
        result = provider.check_model_availability()

        assert result is True
        mock_list.assert_called_once()

    @patch("app.services.llm.ollama_provider.ollama.Client")
    def test_generate_response_success(self, mock_client_class):
        """Test successful response generation."""
        # Mock successful response
        mock_response = {
            "message": {
                "content": "This is a test response.",
            },
        }
        mock_client = mock_client_class.return_value
        mock_client.chat.return_value = mock_response

        provider = OllamaProvider("llama3.2:latest", max_tokens=512, temperature=0.5)
        result = provider.generate_response("Test prompt")

        assert result == "This is a test response."
        mock_client_class.assert_called_once_with(timeout=None)
        mock_client.chat.assert_called_once_with(
            model="llama3.2:latest",
            messages=[{"role": "user", "content": "Test prompt"}],
            options={
                "temperature": 0.5,
                "num_predict": 512,
            },
        )

    @patch("app.services.llm.ollama_provider.ollama.Client")
    def test_generate_response_with_system_prompt(self, mock_client_class):
        """Test response generation with system prompt."""
        # Mock successful response
        mock_response = {
            "message": {
                "content": "This is a test response with system prompt.",
            },
        }
        mock_client = mock_client_class.return_value
        mock_client.chat.return_value = mock_response

        provider = OllamaProvider("llama3.2:latest")
        result = provider.generate_response(
            prompt="Test prompt",
            system_prompt="You are a helpful assistant.",
        )

        assert result == "This is a test response with system prompt."
        mock_client.chat.assert_called_once_with(
            model="llama3.2:latest",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Test prompt"},
            ],
            options={
                "temperature": 0.7,
                "num_predict": 1024,
            },
        )

    @patch("app.services.llm.ollama_provider.ollama.Client")
    def test_generate_response_with_history(self, mock_client_class):
        """Test response generation includes prior conversation turns."""
        mock_client = mock_client_class.return_value
        mock_client.chat.return_value = {"message": {"content": "Sure, following up."}}

        provider = OllamaProvider("llama3.2:latest")
        history = [
            {"role": "user", "content": "What is a residence permit?"},
            {"role": "assistant", "content": "It's a document allowing you to live in Finland."},
        ]
        result = provider.generate_response(
            prompt="How do I apply for one?",
            system_prompt="You are a helpful assistant.",
            history=history,
        )

        assert result == "Sure, following up."
        mock_client.chat.assert_called_once_with(
            model="llama3.2:latest",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is a residence permit?"},
                {"role": "assistant", "content": "It's a document allowing you to live in Finland."},
                {"role": "user", "content": "How do I apply for one?"},
            ],
            options={
                "temperature": 0.7,
                "num_predict": 1024,
            },
        )

    @patch("app.services.llm.ollama_provider.ollama.Client")
    def test_generate_response_history_is_truncated(self, mock_client_class):
        """Test that only the most recent MAX_HISTORY_MESSAGES turns are kept."""
        mock_client = mock_client_class.return_value
        mock_client.chat.return_value = {"message": {"content": "ok"}}

        provider = OllamaProvider("llama3.2:latest")
        history = [{"role": "user", "content": f"message {i}"} for i in range(20)]
        provider.generate_response(prompt="latest question", history=history)

        sent_messages = mock_client.chat.call_args[1]["messages"]
        # All but the final appended user prompt should come from the tail of history
        assert sent_messages[:-1] == history[-10:]
        assert sent_messages[-1] == {"role": "user", "content": "latest question"}

    @patch("app.services.llm.ollama_provider.ollama.Client")
    def test_generate_response_error(self, mock_client_class):
        """Test response generation when an error occurs."""
        # Mock error
        mock_client = mock_client_class.return_value
        mock_client.chat.side_effect = Exception("Connection error")

        provider = OllamaProvider("llama3.2:latest")
        result = provider.generate_response("Test prompt")

        assert "Error: Could not generate a response" in result
        assert "llama3.2:latest" in result
        mock_client.chat.assert_called_once()

    @patch("app.services.llm.ollama_provider.ollama.Client")
    def test_generate_response_passes_timeout_to_the_client(self, mock_client_class):
        """A timeout is enforced by the underlying Ollama HTTP client, not just the caller's await."""
        mock_client = mock_client_class.return_value
        mock_client.chat.return_value = {"message": {"content": "ok"}}

        provider = OllamaProvider("llama3.2:latest")
        provider.generate_response("Test prompt", timeout=5.0)

        mock_client_class.assert_called_once_with(timeout=5.0)

    @patch("app.services.llm.ollama_provider.ollama.Client")
    def test_generate_response_timeout_becomes_a_safe_error_message(self, mock_client_class):
        """A client-side timeout (e.g. httpx.TimeoutException) is caught like any other error."""
        mock_client = mock_client_class.return_value
        mock_client.chat.side_effect = TimeoutError("timed out")

        provider = OllamaProvider("llama3.2:latest")
        result = provider.generate_response("Test prompt", timeout=0.01)

        assert "Error: Could not generate a response" in result

    @patch("app.services.llm.ollama_provider.ollama.chat")
    def test_generate_response_stream_yields_content_without_a_context_cap(self, mock_chat):
        mock_chat.return_value = [
            {"message": {"content": "First "}},
            {"message": {"content": "second"}},
        ]

        chunks = list(OllamaProvider("llama3.2:latest").generate_response_stream("Test prompt"))

        assert chunks == ["First ", "second"]
        options = mock_chat.call_args.kwargs["options"]
        assert "num_ctx" not in options

    @patch("app.services.llm.ollama_provider.ollama.chat")
    def test_generate_response_stream_yields_a_safe_error_message(self, mock_chat):
        mock_chat.side_effect = Exception("Connection error")

        chunks = list(OllamaProvider("llama3.2:latest").generate_response_stream("Test prompt"))

        assert len(chunks) == 1
        assert "Error: Could not generate a response" in chunks[0]

    def test_generate_structured_not_yet_implemented(self):
        """The structured-output hook is defined but unimplemented until #140."""
        from pydantic import BaseModel

        class Schema(BaseModel):
            answer: str

        with pytest.raises(NotImplementedError):
            OllamaProvider("llama3.2:latest").generate_structured("Test prompt", Schema)
