"""LLMProvider implementation backed by a local Ollama instance."""

import logging
from collections.abc import Generator

import ollama

from app.config.settings import DEFAULT_LLM_MODEL
from app.services.llm.base import LLMProvider, build_messages

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """LLMProvider backed by the local Ollama runtime, via the raw ``ollama`` client."""

    def __init__(
        self,
        model_name: str = DEFAULT_LLM_MODEL,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> None:
        """Initialize the provider with the given model settings.

        Args:
            model_name: The name of the Ollama model to use.
            max_tokens: Maximum number of tokens to generate.
            temperature: Temperature parameter for generation.
        """
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        logger.info("Initialized Ollama provider with model: %s", model_name)

    def _describe_match(self, available_model_name: str) -> str | None:
        """Describe how an available model matches the configured model, if at all.

        A model name, including its tag, must match exactly. This prevents a
        configured model such as ``gemma4:latest`` from being treated as an
        installed variant such as ``gemma4:e4b``.

        Args:
            available_model_name: A model name reported by Ollama.

        Returns:
            A log-ready description of the match, or None if it doesn't match.
        """
        if available_model_name == self.model_name:
            return f"Found exact matching model: {available_model_name}"

        return None

    def check_model_availability(self) -> bool:
        """Check if Ollama is running and has the required model.

        Returns:
            bool: True if the model is available, False otherwise.
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
        history: list[dict[str, object]] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Generate a response from the LLM model.

        Args:
            prompt: The prompt to generate a response for
            system_prompt: Optional system prompt to set context
            history: Optional prior conversation turns to include as context
            timeout: Optional request timeout in seconds, enforced by the underlying
                Ollama HTTP client itself (not just the calling coroutine's await) so a
                stalled request actually returns within this bound. ``None`` (the
                default) waits indefinitely, matching Ollama's own client default —
                an ``asyncio.timeout()`` wrapped around a threadpool-dispatched call
                to this method does *not* bound it on its own: AnyIO's
                ``to_thread.run_sync`` ignores cancellation by default and waits for
                the worker thread to finish regardless, so passing this parameter is
                the only way for a caller to actually bound the call.

        Returns:
            str: The generated response
        """
        try:
            messages = build_messages(prompt, system_prompt, history)

            response = ollama.Client(timeout=timeout).chat(
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
        history: list[dict[str, object]] | None = None,
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
            messages = build_messages(prompt, system_prompt, history)

            # Use streaming chat with optimized options for faster response
            logger.info("About to call ollama.chat with streaming")
            stream = ollama.chat(
                model=self.model_name,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
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
