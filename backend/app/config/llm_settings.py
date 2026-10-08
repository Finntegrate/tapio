"""Environment-driven LLM provider configuration (#9, #139)."""

from typing import Final

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.agents.definitions import AGENTS_BY_ID
from app.config.settings import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER

GUARDRAIL_ROLE: Final = "guardrail"
"""Override key for the guardrail stage: classification and the localized response intro."""

MODEL_OVERRIDE_ROLES: Final = frozenset({*AGENTS_BY_ID, GUARDRAIL_ROLE})
"""Every key ``TAPIO_LLM_MODEL_OVERRIDES`` accepts: a guide id, or a non-guide LLM stage."""


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
        api_base: Optional custom API base URL. For ``"ollama"``, points at a remote or
            non-default Ollama server. Required for Scaleway's Generative APIs and other
            self-hosted OpenAI-compatible endpoints (used with ``provider="openai"``);
            unused by OpenAI/Anthropic's own default endpoints.
        api_key: Optional explicit API key. When unset, each provider's LangChain
            integration falls back to its own standard environment variable (e.g.
            ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``).
        model_overrides: Optional per-guide/per-stage model selection (#139), read from
            ``TAPIO_LLM_MODEL_OVERRIDES`` as a JSON object. Keys are a guide id (e.g.
            ``"sampo"``) or ``"guardrail"``; values use LangChain's own ``provider:model``
            form (e.g. ``"anthropic:claude-haiku-4-5"``), or a bare model name to keep
            ``provider``. Anything without an entry uses ``provider``/``model``.
    """

    model_config = SettingsConfigDict(env_prefix="TAPIO_LLM_")

    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    api_base: str | None = None
    api_key: SecretStr | None = None
    model_overrides: dict[str, str] = {}

    @field_validator("model_overrides")
    @classmethod
    def _reject_unknown_roles(cls, value: dict[str, str]) -> dict[str, str]:
        """Fail at startup on a mistyped key, rather than silently using the default model.

        Args:
            value: The parsed ``TAPIO_LLM_MODEL_OVERRIDES`` mapping.

        Returns:
            ``value``, unchanged.

        Raises:
            ValueError: If a key is neither a guide id nor ``"guardrail"``.
        """
        unknown = sorted(set(value) - MODEL_OVERRIDE_ROLES)
        if unknown:
            msg = f"Unknown TAPIO_LLM_MODEL_OVERRIDES keys {unknown}; expected any of {sorted(MODEL_OVERRIDE_ROLES)}"
            raise ValueError(msg)
        return value
