"""Per-provider configuration shared by ``chat_model`` and the guardrail classifier (#146).

Adding a provider used to mean touching four separate provider-keyed maps across two
files: the max-tokens kwarg, base-URL fallback env vars, and credential env var in
``app.services.chat_model``, plus the infra-error exception types in
``app.guardrails.llm_classifier``. This module is the single per-provider table both
read from instead.
"""

from dataclasses import dataclass
from typing import Final

import anthropic
import ollama
import openai
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Everything that varies by LLM provider (``config.llm_provider``)."""

    model_type: type[BaseChatModel]

    # init_chat_model forwards kwargs verbatim, so a provider whose max-output-length
    # field isn't named max_tokens (e.g. ChatOllama's num_predict) has to be mapped.
    max_tokens_kwarg: str = "max_tokens"

    # Each provider's own SDK falls back to these env vars for its API base URL when
    # neither an explicit kwarg nor TAPIO_LLM_API_BASE is set. The cleartext-transport
    # guard in chat_model.py has to check the URL that will actually be used, not just
    # TAPIO_LLM_API_BASE, or one of these — already set for an unrelated reason, e.g. a
    # devbox's OLLAMA_HOST — could route prompts and credentials over plain HTTP without
    # Tapio's own config layer ever seeing it.
    base_url_env_vars: tuple[str, ...] = ()

    # The env var this provider's own SDK reads credentials from by default — used only
    # to answer "is this provider configured" for /health, since construction alone
    # doesn't reliably tell us (ChatOpenAI raises if the key is missing, ChatAnthropic
    # doesn't). None for a provider with no such notion (Ollama has no API key).
    credential_env_var: str | None = None

    # Exception types this provider's SDK raises for connection/timeout/server-level
    # failures, as opposed to a response that just didn't fit the expected schema — see
    # app.guardrails.llm_classifier's module docstring for why that distinction matters.
    infra_error_types: tuple[type[Exception], ...] = ()


PROVIDERS: Final[dict[str, ProviderConfig]] = {
    "ollama": ProviderConfig(
        model_type=ChatOllama,
        max_tokens_kwarg="num_predict",
        # ollama.Client reads OLLAMA_HOST as its API base fallback.
        base_url_env_vars=("OLLAMA_HOST",),
        infra_error_types=(ollama.ResponseError,),
    ),
    "openai": ProviderConfig(
        model_type=ChatOpenAI,
        # ChatOpenAI reads OPENAI_API_BASE then OPENAI_BASE_URL as its API base fallback.
        base_url_env_vars=("OPENAI_API_BASE", "OPENAI_BASE_URL"),
        credential_env_var="OPENAI_API_KEY",
        # openai's own *TimeoutError subclasses APIConnectionError, so catching the
        # connection error covers both. APIStatusError (401/429/5xx, ...) is a separate
        # sibling class, not a subclass of APIConnectionError, so it needs listing
        # explicitly.
        infra_error_types=(openai.APIConnectionError, openai.APIStatusError),
    ),
    "anthropic": ProviderConfig(
        model_type=ChatAnthropic,
        # ChatAnthropic reads ANTHROPIC_API_URL then ANTHROPIC_BASE_URL as its API base
        # fallback.
        base_url_env_vars=("ANTHROPIC_API_URL", "ANTHROPIC_BASE_URL"),
        credential_env_var="ANTHROPIC_API_KEY",
        infra_error_types=(anthropic.APIConnectionError, anthropic.APIStatusError),
    ),
}
