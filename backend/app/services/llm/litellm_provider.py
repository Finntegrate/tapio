"""LLMProvider implementation covering OpenAI, Anthropic, Scaleway, and other OpenAI-compatible endpoints.

All of it goes through LiteLLM's single ``completion`` call. The model
string selects the vendor LiteLLM talks to (e.g.
``"openai/gpt-4o-mini"``, ``"anthropic/claude-3-5-haiku-20241022"``); an
OpenAI-compatible endpoint with no dedicated LiteLLM vendor prefix — such as
Scaleway's Generative APIs — uses the ``"openai/<model-id>"`` prefix together
with ``api_base`` pointed at that endpoint. See ``app.config.llm_settings``
for how ``TAPIO_LLM_MODEL``/``TAPIO_LLM_API_BASE``/``TAPIO_LLM_API_KEY`` map
onto this provider's constructor.
"""

import logging
from collections.abc import Generator

import litellm

from app.services.llm.base import LLMProvider, build_messages

logger = logging.getLogger(__name__)


class LiteLLMProvider(LLMProvider):
    """LLMProvider backed by LiteLLM, covering any OpenAI-compatible cloud endpoint."""

    def __init__(
        self,
        model_name: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialize the provider with the given model settings.

        Args:
            model_name: A LiteLLM model string, e.g. ``"openai/gpt-4o-mini"``,
                ``"anthropic/claude-3-5-haiku-20241022"``, or ``"openai/<model-id>"``
                for an OpenAI-compatible endpoint used together with ``api_base``.
            max_tokens: Maximum number of tokens to generate.
            temperature: Temperature parameter for generation.
            api_base: Optional custom API base URL (required for Scaleway and other
                self-hosted OpenAI-compatible endpoints).
            api_key: Optional explicit API key. When ``None``, LiteLLM falls back to
                the provider's standard environment variable (e.g. ``OPENAI_API_KEY``).
        """
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.api_base = api_base
        self.api_key = api_key
        logger.info("Initialized LiteLLM provider with model: %s", model_name)

    def check_model_availability(self) -> bool:
        """Check whether credentials for this model's provider are configured.

        This intentionally does not make a live API call — unlike Ollama's local
        model list, a cloud provider check would cost money on every ``/health``
        poll. An explicit ``api_key`` (passed directly to every call) is treated
        as available without consulting the environment; otherwise LiteLLM's own
        environment-variable requirements for the model are checked.

        Returns:
            bool: True if the provider appears ready to serve requests.
        """
        if self.api_key:
            return True

        try:
            report = litellm.validate_environment(self.model_name)
        except Exception:
            logger.warning("Could not validate LiteLLM environment for model %s", self.model_name, exc_info=True)
            return False

        missing_keys = report.get("missing_keys")
        if missing_keys:
            logger.warning(
                "LiteLLM provider for model %s is missing environment variables: %s",
                self.model_name,
                ", ".join(missing_keys),
            )
        return bool(report.get("keys_in_environment"))

    def generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, object]] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Generate a response from the configured LiteLLM model.

        Args:
            prompt: The prompt to generate a response for.
            system_prompt: Optional system prompt to set context.
            history: Optional prior conversation turns to include as context.
            timeout: Optional request timeout in seconds, passed straight to LiteLLM.

        Returns:
            str: The generated response.
        """
        try:
            messages = build_messages(prompt, system_prompt, history)

            response = litellm.completion(
                model=self.model_name,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                api_base=self.api_base,
                api_key=self.api_key,
                timeout=timeout,
            )
            return response.choices[0].message.content or ""
        except Exception:
            logger.exception("Error generating response")
            return f"Error: Could not generate a response. Please check the {self.model_name} provider configuration."

    def generate_response_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, object]] | None = None,
    ) -> Generator[str]:
        """Generate a streaming response from the configured LiteLLM model.

        Args:
            prompt: The prompt to generate a response for.
            system_prompt: Optional system prompt to set context.
            history: Optional prior conversation turns to include as context.

        Yields:
            str: Chunks of the generated response.
        """
        try:
            messages = build_messages(prompt, system_prompt, history)

            stream = litellm.completion(
                model=self.model_name,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                api_base=self.api_base,
                api_key=self.api_key,
                stream=True,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception:
            logger.exception("Error generating streaming response")
            yield (f"Error: Could not generate a response. Please check the {self.model_name} provider configuration.")
