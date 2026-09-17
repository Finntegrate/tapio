"""Environment-driven LLM provider configuration (#9)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.settings import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER


class LLMSettings(BaseSettings):
    """Which LLM provider and model to use, and how to reach it.

    Layered alongside ``BackendSettings`` but kept separate: this configures the
    LLM backend the RAG pipeline and guardrail classifier generate with, not the
    HTTP server itself.

    Args:
        provider: ``"ollama"`` for the local Ollama runtime, or ``"litellm"`` for
            any of the cloud/OpenAI-compatible backends ``LiteLLMProvider`` covers
            (OpenAI, Anthropic, Scaleway, and other OpenAI-compatible endpoints).
        model: The model identifier. For ``"ollama"``, a plain Ollama model tag
            (e.g. ``"gemma4:latest"``). For ``"litellm"``, a LiteLLM model string
            (e.g. ``"openai/gpt-4o-mini"``, ``"anthropic/claude-3-5-haiku-20241022"``,
            or ``"openai/<model-id>"`` together with ``api_base`` pointed at
            Scaleway's OpenAI-compatible endpoint).
        api_base: Optional custom API base URL, passed straight to LiteLLM.
            Required for Scaleway and other self-hosted OpenAI-compatible
            endpoints; unused by ``"ollama"`` and by providers LiteLLM already
            knows the default endpoint for (OpenAI, Anthropic).
        api_key: Optional explicit API key, passed straight to LiteLLM. When
            unset, LiteLLM falls back to the provider's standard environment
            variable (e.g. ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``).
    """

    model_config = SettingsConfigDict(env_prefix="TAPIO_LLM_")

    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    api_base: str | None = None
    api_key: SecretStr | None = None
