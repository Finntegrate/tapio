"""Environment-driven LLM provider configuration (#9, #139)."""

from typing import Final, Self

from langchain.chat_models import base as langchain_chat_models
from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.agents.definitions import AGENTS_BY_ID
from app.config.settings import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER

GUARDRAIL_ROLE: Final = "guardrail"
"""Override key for the guardrail stage: classification and the localized response intro."""

MODEL_OVERRIDE_ROLES: Final = frozenset({*AGENTS_BY_ID, GUARDRAIL_ROLE})
"""Every key ``TAPIO_LLM_MODEL_OVERRIDES`` accepts: a guide id, or a non-guide LLM stage."""

# Every provider name init_chat_model recognizes. LangChain keeps the list private, so
# tests/config/test_llm_settings.py fails if an upgrade renames it, rather than this
# silently becoming empty and letting unsupported providers through again.
LANGCHAIN_PROVIDERS: Final[frozenset[str]] = frozenset(getattr(langchain_chat_models, "_BUILTIN_PROVIDERS", ()))


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

    @model_validator(mode="after")
    def _reject_unsupported_override_providers(self) -> Self:
        """Fail at startup on an override that would silently reach the wrong provider.

        ``resolve_model`` reads a value whose prefix isn't a Tapio provider as a bare model
        name on the default provider, which keeps Ollama tags such as ``gemma4:e2b`` working.
        Without this check, a typo (``antropic:...``) or a provider LangChain supports but
        Tapio doesn't (``google_genai:...``) would be sent to the default provider under a
        nonsense model id, failing only at request time, and failing open for the guardrail.

        Returns:
            ``self``, unchanged.

        Raises:
            ValueError: If an override names a provider Tapio doesn't support, a near-miss of
                one it does, or an unknown prefix while the default provider isn't Ollama.
        """
        # Imported here: app.services imports app.config, so a module-level import would be circular.
        from app.services.llm_providers import PROVIDERS  # noqa: PLC0415

        supported = sorted(PROVIDERS)
        for role, value in self.model_overrides.items():
            prefix, separator, _model = value.partition(":")
            if not separator or prefix in PROVIDERS:
                continue
            where = f"TAPIO_LLM_MODEL_OVERRIDES[{role!r}] = {value!r}"
            if prefix in LANGCHAIN_PROVIDERS:
                msg = f"{where}: provider {prefix!r} is not supported by Tapio; supported providers are {supported}"
                raise ValueError(msg)
            near_miss = next((name for name in supported if _one_edit_apart(prefix, name)), None)
            if near_miss:
                msg = f"{where}: unknown provider {prefix!r}; did you mean {near_miss!r}?"
                raise ValueError(msg)
            if self.provider != "ollama":
                msg = (
                    f"{where}: {prefix!r} is not a provider. A bare model name is only accepted on an "
                    f"Ollama default; prefix the value with one of {supported} (e.g. 'openai:{value}')."
                )
                raise ValueError(msg)
        return self


def _one_edit_apart(a: str, b: str) -> bool:
    """Whether ``a`` becomes ``b`` with one insertion, deletion, substitution, or adjacent swap.

    Deliberately tight: a looser similarity would flag real Ollama tags, e.g. ``llama3`` is
    two edits from ``ollama``.
    """
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        if sum(x != y for x, y in zip(a, b, strict=True)) == 1:
            return True
        return any(a[:i] + a[i + 1] + a[i] + a[i + 2 :] == b for i in range(len(a) - 1))
    shorter, longer = sorted((a, b), key=len)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))
