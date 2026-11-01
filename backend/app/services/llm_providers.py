"""Per-provider configuration shared by ``chat_model`` and the guardrail classifier (#146).

Adding a provider used to mean touching four separate provider-keyed maps across two
files: the max-tokens kwarg, base-URL fallback env vars, and credential env var in
``app.services.chat_model``, plus the infra-error exception types in
``app.guardrails.llm_classifier``. This module is the single per-provider table both
read from instead — including the ways a provider's constructor kwargs differ from
the common case, such as how the request timeout is wired (#164).
"""

from dataclasses import dataclass
from typing import Any, Final

import anthropic
import ollama
import openai
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

# The constructor kwarg carrying the request timeout for a provider that takes it
# top-level, which is what LangChain's own provider integrations expect.
DEFAULT_TIMEOUT_KWARG: Final = "timeout"


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Everything that varies by LLM provider (``config.llm_provider``).

    Args:
        model_type: The LangChain ``BaseChatModel`` subclass this provider constructs.
        max_tokens_kwarg: The constructor kwarg name for the output-length cap.
        timeout_kwarg: The constructor kwarg name carrying the request timeout, or
            ``None`` for a provider whose chat model has no top-level timeout field
            and takes the timeout nested under ``client_kwargs`` instead.
        base_url_env_vars: Env vars this provider's own SDK falls back to for its API
            base URL, in fallback order.
        credential_env_var: The env var this provider's own SDK reads its credential
            from, or ``None`` for a provider with no such notion.
        infra_error_types: Exception types this provider's SDK raises for
            connection/timeout/server-level failures.
    """

    model_type: type[BaseChatModel]

    # init_chat_model forwards kwargs verbatim, so a provider whose max-output-length
    # field isn't named max_tokens (e.g. ChatOllama's num_predict) has to be mapped.
    max_tokens_kwarg: str = "max_tokens"

    # The constructor kwarg carrying the request timeout, or None for a provider whose
    # chat model has no top-level timeout field: ChatOllama's request timeout belongs
    # to its underlying httpx client, so it goes through `client_kwargs`, forwarded
    # verbatim — a bare `timeout=` kwarg is silently dropped.
    timeout_kwarg: str | None = DEFAULT_TIMEOUT_KWARG

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
        # ChatOllama has no top-level timeout field — its request timeout goes to the
        # underlying httpx client through client_kwargs.
        timeout_kwarg=None,
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


def apply_timeout(provider: ProviderConfig | None, kwargs: dict[str, Any], timeout: float) -> None:
    """Apply a request timeout to constructor kwargs the way the provider takes it.

    A provider whose chat model has no top-level timeout field has its timeout nested
    under ``client_kwargs`` instead, which LangChain forwards verbatim to the
    provider's underlying HTTP client. Which of the two applies is a per-provider
    table entry, so no caller needs a provider-specific branch (#164).

    Args:
        provider: The provider's table entry, or ``None`` for a provider LangChain
            supports but Tapio has no entry for — those take the plain top-level
            ``timeout`` kwarg.
        kwargs: The constructor kwargs to add the timeout to, in place.
        timeout: The request timeout in seconds.
    """
    timeout_kwarg = provider.timeout_kwarg if provider else DEFAULT_TIMEOUT_KWARG
    if timeout_kwarg is None:
        kwargs["client_kwargs"] = {"timeout": timeout}
    else:
        kwargs[timeout_kwarg] = timeout
