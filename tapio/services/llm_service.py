"""Service for interacting with LLM models through Ollama."""

import logging
from collections.abc import Generator
from typing import Any

import ollama

# Configure logging
logger = logging.getLogger(__name__)

# Cap on prior turns included as context, to avoid overflowing the model's context window
MAX_HISTORY_MESSAGES = 10


def _build_messages(
    prompt: str,
    system_prompt: str | None,
    history: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Build the ollama chat messages list from a prompt, optional system prompt, and history.

    Args:
        prompt: The current user prompt
        system_prompt: Optional system prompt to set context
        history: Optional prior conversation turns (role/content dicts)

    Returns:
        Messages list ready to pass to `ollama.chat`
    """
    messages: list[dict[str, Any]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if history:
        messages.extend(history[-MAX_HISTORY_MESSAGES:])

    messages.append({"role": "user", "content": prompt})
    return messages


class LLMService:
    """Service for interacting with LLM models through Ollama."""

    def __init__(
        self,
        model_name: str = "llama3.2",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> None:
        """Initialize the LLM service with the given model settings.

        Args:
            model_name: The name of the model to use
            max_tokens: Maximum number of tokens to generate
            temperature: Temperature parameter for generation
        """
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        logger.info("Initialized LLM service with model: %s", model_name)

    def _describe_match(self, available_model_name: str) -> str | None:
        """Describe how an available model matches the configured model, if at all.

        Handles exact matches and `:tag` variations (e.g. requesting "llama3.2" should
        match an available "llama3.2:latest").

        Args:
            available_model_name: A model name reported by Ollama

        Returns:
            A log-ready description of the match, or None if it doesn't match
        """
        if available_model_name == self.model_name:
            return f"Found exact matching model: {available_model_name}"

        # If user provided base name (no tag), match any variant with tags
        if ":" not in self.model_name and available_model_name.startswith(f"{self.model_name}:"):
            return f"Found matching model: {available_model_name} for base name {self.model_name}"

        # If user provided name with tag, check if base names match
        if ":" in self.model_name and ":" in available_model_name:
            user_base = self.model_name.split(":")[0]
            model_base = available_model_name.split(":", maxsplit=1)[0]
            if user_base == model_base:
                return f"Found matching model: {available_model_name} for requested {self.model_name}"

        return None

    def check_model_availability(self) -> bool:
        """Check if Ollama is running and has the required model.

        Returns:
            bool: True if the model is available, False otherwise
        """
        try:
            models_response = ollama.list()

            if not hasattr(models_response, "models") or not models_response.models:
                logger.warning("No models found in Ollama")
                return False

            # Extract model names from the Model objects
            available_models = [model_obj.model for model_obj in models_response.models if model_obj.model]
            logger.info("Available Ollama models: %s", ", ".join(available_models))

            match_descriptions = (self._describe_match(m) for m in available_models)
            match = next((description for description in match_descriptions if description), None)
            if match is None:
                logger.warning(
                    "%s model not found in Ollama. Please pull it with 'ollama pull %s'",
                    self.model_name,
                    self.model_name,
                )
                return False
            logger.info(match)
        except Exception as e:
            logger.warning("Could not connect to Ollama: %s", e)
            logger.warning("Make sure Ollama is running")
            return False
        else:
            return True

    def generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> str | dict:
        """Generate a response from the LLM model.

        Args:
            prompt: The prompt to generate a response for
            system_prompt: Optional system prompt to set context
            history: Optional prior conversation turns to include as context

        Returns:
            str: The generated response
        """
        try:
            messages = _build_messages(prompt, system_prompt, history)

            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            )
            return response["message"]["content"]
        except Exception:
            logger.exception("Error generating response")
            return (
                f"Error: Could not generate a response. "
                f"Please check if Ollama is running with the {self.model_name} model."
            )

    def generate_response_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> Generator[str]:
        """Generate a streaming response from the LLM model.

        Args:
            prompt: The prompt to generate a response for
            system_prompt: Optional system prompt to set context
            history: Optional prior conversation turns to include as context

        Yields:
            str: Chunks of the generated response
        """
        try:
            messages = _build_messages(prompt, system_prompt, history)

            # Use streaming chat with optimized options for faster response
            logger.info("About to call ollama.chat with streaming")
            stream = ollama.chat(
                model=self.model_name,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                    "num_ctx": 2048,  # Reduce context window for faster processing
                    "top_k": 40,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "seed": -1,
                    "num_thread": 0,  # Use all available threads
                },
                stream=True,
                keep_alive="5m",  # Keep model loaded for faster subsequent requests
            )

            logger.info("Starting to iterate over ollama stream")
            for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    content = chunk["message"]["content"]
                    logger.debug("LLM yielding chunk of %d characters", len(content))
                    yield content

        except Exception:
            logger.exception("Error generating streaming response")
            yield (
                f"Error: Could not generate a response. "
                f"Please check if Ollama is running with the {self.model_name} model."
            )

    def get_model_name(self) -> str:
        """Get the name of the model being used.

        Returns:
            str: The model name
        """
        return self.model_name
