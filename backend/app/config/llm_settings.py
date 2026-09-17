"""Environment-driven LLM provider configuration (#9)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.settings import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER


class LLMSettings(BaseSettings):
    """Which LLM provider and model to use, and how to reach it.

    Layered alongside ``BackendSettings`` but kept separate: this configures the
    LLM backend the RAG pipeline and guardrail classifier generate with, not the
    HTTP server itself. ``provider`` is passed straight through to LangChain's
    ``init_chat_model(model, model_provider=provider, ...)`` (see
    ``app.services.chat_model.build_chat_model``), so its values are exactly the
    provider names LangChain itself recognizes, not a Tapio-specific vocabulary.

    Args:
        provider: ``"ollama"`` for the local Ollama runtime, ``"openai"`` for OpenAI
            (or any OpenAI-compatible endpoint, via ``api_base`` — see Scaleway below),
            or ``"anthropic"`` for Anthropic.
        model: The model identifier, in whatever form the chosen provider expects
            (e.g. ``"gemma4:latest"`` for Ollama, ``"gpt-4o-mini"`` for OpenAI,
            ``"claude-3-5-haiku-20241022"`` for Anthropic).
        api_base: Optional custom API base URL. Required for Scaleway's Generative
            APIs and other self-hosted OpenAI-compatible endpoints (used with
            ``provider="openai"``); unused by ``"ollama"`` and by OpenAI/Anthropic's
            own default endpoints.
        api_key: Optional explicit API key. When unset, each provider's LangChain
            integration falls back to its own standard environment variable (e.g.
            ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``).
    """

    model_config = SettingsConfigDict(env_prefix="TAPIO_LLM_")

    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    api_base: str | None = None
    api_key: SecretStr | None = None
