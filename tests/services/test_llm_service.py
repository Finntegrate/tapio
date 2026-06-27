"""Tests for the LLM service module."""

from unittest.mock import MagicMock, patch

import pytest

from tapio.services.llm_service import LLMService


class TestLLMService:
    """Tests for the LLMService class."""

    def test_init(self):
        """Test LLMService initialization with default parameters."""
        service = LLMService()

        assert service.model_name == "llama3.2"
        assert service.max_tokens == 1024
        assert service.temperature == 0.7

    def test_init_with_custom_parameters(self):
        """Test LLMService initialization with custom parameters."""
        service = LLMService(
            model_name="llama3.2:latest",
            max_tokens=2048,
            temperature=0.5,
        )

        assert service.model_name == "llama3.2:latest"
        assert service.max_tokens == 2048
        assert service.temperature == 0.5

    def test_get_model_name(self):
        """Test getting the model name."""
        service = LLMService(model_name="test-model")
        assert service.get_model_name() == "test-model"

    @patch("tapio.services.llm_service.ollama.list")
    def test_check_model_availability_no_models(self, mock_list):
        """Test model availability check when no models are available."""
        # Mock empty response
        mock_response = MagicMock()
        mock_response.models = []
        mock_list.return_value = mock_response

        service = LLMService("llama3.2")
        result = service.check_model_availability()

        assert result is False
        mock_list.assert_called_once()

    @patch("tapio.services.llm_service.ollama.list")
    def test_check_model_availability_ollama_not_running(self, mock_list):
        """Test model availability check when Ollama is not running."""
        # Mock connection error
        mock_list.side_effect = Exception("Connection refused")

        service = LLMService("llama3.2")
        result = service.check_model_availability()

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
            # Base name matching (user provides base name, model has tag)
            (
                "llama3.2",
                ["llama3.2:latest", "all-minilm:22m"],
                True,
                "Found matching model: llama3.2:latest for base name llama3.2",
            ),
            (
                "all-minilm",
                ["llama3.2:latest", "all-minilm:22m"],
                True,
                "Found matching model: all-minilm:22m for base name all-minilm",
            ),
            # Base name matching (user provides tag, model has different tag but same base)
            (
                "llama3.2:3b",
                ["llama3.2:latest", "all-minilm:22m"],
                True,
                "Found matching model: llama3.2:latest for requested llama3.2:3b",
            ),
            (
                "llama3.2:latest",
                ["llama3.2:3b", "all-minilm:22m"],
                True,
                "Found matching model: llama3.2:3b for requested llama3.2:latest",
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
            # Edge cases with complex model names
            (
                "llama3.2",
                ["llama3.2:latest", "llama3.2:3b", "llama3.2:instruct"],
                True,
                "Found matching model: llama3.2:latest for base name llama3.2",
            ),
            (
                "codellama:7b-instruct",
                ["codellama:13b-instruct", "llama3.2:latest"],
                True,
                "Found matching model: codellama:13b-instruct for requested codellama:7b-instruct",
            ),
        ],
    )
    @patch("tapio.services.llm_service.ollama.list")
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

        caplog.set_level(logging.INFO, logger="tapio.services.llm_service")

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

        service = LLMService(requested_model)
        result = service.check_model_availability()

        assert result is expected_result
        mock_list.assert_called_once()

        # Check that the expected log message appears
        assert expected_log_message in caplog.text

    @patch("tapio.services.llm_service.ollama.list")
    def test_check_model_availability_logs_available_models(self, mock_list, caplog):
        """Test that available models are logged correctly."""
        # Configure logging for the test
        import logging

        caplog.set_level(logging.INFO, logger="tapio.services.llm_service")

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

        service = LLMService("llama3.2:latest")
        service.check_model_availability()

        # Check that all available models are logged
        expected_log = "Available Ollama models: llama3.2:latest, all-minilm:22m, codellama:7b"
        assert expected_log in caplog.text

    @patch("tapio.services.llm_service.ollama.list")
    def test_check_model_availability_handles_none_model_names(self, mock_list):
        """Test that the service handles model objects with None names gracefully."""
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

        service = LLMService("llama3.2:latest")
        result = service.check_model_availability()

        assert result is True
        mock_list.assert_called_once()

    @patch("tapio.services.llm_service.ollama.chat")
    def test_generate_response_success(self, mock_chat):
        """Test successful response generation."""
        # Mock successful response
        mock_response = {
            "message": {
                "content": "This is a test response.",
            },
        }
        mock_chat.return_value = mock_response

        service = LLMService("llama3.2:latest", max_tokens=512, temperature=0.5)
        result = service.generate_response("Test prompt")

        assert result == "This is a test response."
        mock_chat.assert_called_once_with(
            model="llama3.2:latest",
            messages=[{"role": "user", "content": "Test prompt"}],
            options={
                "temperature": 0.5,
                "num_predict": 512,
            },
        )

    @patch("tapio.services.llm_service.ollama.chat")
    def test_generate_response_with_system_prompt(self, mock_chat):
        """Test response generation with system prompt."""
        # Mock successful response
        mock_response = {
            "message": {
                "content": "This is a test response with system prompt.",
            },
        }
        mock_chat.return_value = mock_response

        service = LLMService("llama3.2:latest")
        result = service.generate_response(
            prompt="Test prompt",
            system_prompt="You are a helpful assistant.",
        )

        assert result == "This is a test response with system prompt."
        mock_chat.assert_called_once_with(
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

    @patch("tapio.services.llm_service.ollama.chat")
    def test_generate_response_with_history(self, mock_chat):
        """Test response generation includes prior conversation turns."""
        mock_chat.return_value = {"message": {"content": "Sure, following up."}}

        service = LLMService("llama3.2:latest")
        history = [
            {"role": "user", "content": "What is a residence permit?"},
            {"role": "assistant", "content": "It's a document allowing you to live in Finland."},
        ]
        result = service.generate_response(
            prompt="How do I apply for one?",
            system_prompt="You are a helpful assistant.",
            history=history,
        )

        assert result == "Sure, following up."
        mock_chat.assert_called_once_with(
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

    @patch("tapio.services.llm_service.ollama.chat")
    def test_generate_response_history_is_truncated(self, mock_chat):
        """Test that only the most recent MAX_HISTORY_MESSAGES turns are kept."""
        mock_chat.return_value = {"message": {"content": "ok"}}

        service = LLMService("llama3.2:latest")
        history = [{"role": "user", "content": f"message {i}"} for i in range(20)]
        service.generate_response(prompt="latest question", history=history)

        sent_messages = mock_chat.call_args[1]["messages"]
        # All but the final appended user prompt should come from the tail of history
        assert sent_messages[:-1] == history[-10:]
        assert sent_messages[-1] == {"role": "user", "content": "latest question"}

    @patch("tapio.services.llm_service.ollama.chat")
    def test_generate_response_error(self, mock_chat):
        """Test response generation when an error occurs."""
        # Mock error
        mock_chat.side_effect = Exception("Connection error")

        service = LLMService("llama3.2:latest")
        result = service.generate_response("Test prompt")

        assert "Error: Could not generate a response" in result
        assert "llama3.2:latest" in result
        mock_chat.assert_called_once()
