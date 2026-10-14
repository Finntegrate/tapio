"""Environment-driven LLM provider configuration (#9, #139)."""

from difflib import get_close_matches
from typing import Final

from pydantic import SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.agents.definitions import AGENTS_BY_ID
from app.config.settings import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER

GUARDRAIL_ROLE: Final = "guardrail"
"""Override key for the guardrail stage: classification and the localized response intro."""

MODEL_OVERRIDE_ROLES: Final = frozenset({*AGENTS_BY_ID, GUARDRAIL_ROLE})
"""Every key ``TAPIO_LLM_MODEL_OVERRIDES`` accepts: a guide id, or a non-guide LLM stage."""


SUPPORTED_MODEL_PROVIDERS: Final = frozenset({"ollama", "openai", "anthropic"})
"""Providers Tapio has configured integrations for."""

LANGCHAIN_MODEL_PROVIDERS: Final = frozenset(
    {
        "openai",
        "anthropic",
        "azure_openai",
        "azure_ai",
        "google_vertexai",
        "google_genai",
        "anthropic_bedrock",
        "bedrock",
        "bedrock_converse",
        "cohere",
        "fireworks",
        "together",
        "mistralai",
        "huggingface",
        "groq",
        "ollama",
        "google_anthropic_vertex",
        "deepseek",
        "ibm",
        "nvidia",
        "xai",
        "openrouter",
        "perplexity",
        "upstage",
        "baseten",
        "litellm",
        "meta",
        "langsmith",
    }
)
"""Provider prefixes recognized by the installed LangChain interface."""


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
    def _validate_model_overrides(cls, value: dict[str, str], info: ValidationInfo) -> dict[str, str]:
        """Validate override roles and provider prefixes at startup."""
        unknown_roles = sorted(set(value) - MODEL_OVERRIDE_ROLES)
        if unknown_roles:
            msg = (
                f"Unknown TAPIO_LLM_MODEL_OVERRIDES keys {unknown_roles}; "
                f"expected any of {sorted(MODEL_OVERRIDE_ROLES)}"
            )
            raise ValueError(msg)

        default_provider = info.data.get("provider", DEFAULT_LLM_PROVIDER)

        for role, override in value.items():
            prefix, separator, model_name = override.partition(":")
            if not separator:
                continue

            if prefix in SUPPORTED_MODEL_PROVIDERS:
                if not model_name.strip():
                    msg = (
                        f"Invalid TAPIO_LLM_MODEL_OVERRIDES value for {role!r}: "
                        f"provider {prefix!r} requires a model name"
                    )
                    raise ValueError(msg)
                continue

            if prefix in LANGCHAIN_MODEL_PROVIDERS:
                msg = (
                    f"Unsupported provider {prefix!r} in TAPIO_LLM_MODEL_OVERRIDES "
                    f"for {role!r}. Supported providers: "
                    f"{sorted(SUPPORTED_MODEL_PROVIDERS)}"
                )
                raise ValueError(msg)

            likely_typo = get_close_matches(prefix.lower(), sorted(SUPPORTED_MODEL_PROVIDERS), n=1, cutoff=0.78)
            if likely_typo:
                msg = (
                    f"Unknown provider prefix {prefix!r} in TAPIO_LLM_MODEL_OVERRIDES "
                    f"for {role!r}. Did you mean {likely_typo[0]!r}? "
                    f"Supported providers: {sorted(SUPPORTED_MODEL_PROVIDERS)}"
                )
                raise ValueError(msg)

            # Ollama model identifiers commonly contain a colon for their tag,
            # for example gemma4:e2b. Preserve unknown tags for the Ollama default.
            if default_provider == "ollama":
                continue

            msg = (
                f"Unknown provider prefix {prefix!r} in TAPIO_LLM_MODEL_OVERRIDES "
                f"for {role!r}. Supported providers: {sorted(SUPPORTED_MODEL_PROVIDERS)}"
            )
            raise ValueError(msg)

        return value
