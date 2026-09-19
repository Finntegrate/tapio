"""Build and use the configured LangChain chat model (#9).

Rather than a bespoke provider abstraction, the LLM backend is a plain
``BaseChatModel`` (``langchain-core``), selected at runtime through
``init_chat_model`` — LangChain's own config-driven provider factory.
``ChatOllama``, ``ChatOpenAI``, and ``ChatAnthropic`` already implement
``invoke``/``stream``/``with_structured_output`` uniformly, so every call
site (``RAGOrchestrator``, the graph's generation node, the guardrail
response builder) depends on ``BaseChatModel`` directly. Swapping providers
is a ``TAPIO_LLM_PROVIDER``/``TAPIO_LLM_MODEL`` env var change, not a code
change — see ``app.config.llm_settings`` and ``backend/README.md``.

The only things LangChain doesn't hand us for free are Tapio-specific: the
env-var-to-constructor-kwarg wiring (``build_chat_model``), a live
availability check for ``/health`` (``check_model_availability``), and
converting this app's UI chat-history format (structured content blocks)
into the plain role/content dicts a chat model's ``invoke``/``stream``
accept (the ``build_messages`` family below).
"""

import logging
import os
from collections.abc import Generator
from typing import Any, Final
from urllib.parse import urlparse

import ollama
from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.config.config_models import RAGConfig
from app.config.llm_settings import LLMSettings

logger = logging.getLogger(__name__)

# Hosts plain HTTP is safe against: no network hop for a credential to leak from.
_LOOPBACK_HOSTS: Final = {"localhost", "127.0.0.1", "::1"}

# Cap on prior turns included as context, to avoid overflowing the model's context window.
MAX_HISTORY_MESSAGES = 10

# ChatOllama's max-output-length field is named num_predict, not max_tokens like every
# other provider — init_chat_model forwards kwargs verbatim, so this has to be mapped.
_MAX_TOKENS_KWARG_BY_PROVIDER: dict[str, str] = {"ollama": "num_predict"}

# ChatOllama has no top-level `timeout` field — a bare `timeout=` kwarg is silently
# dropped. Its request timeout instead goes through `client_kwargs`, forwarded verbatim
# to the underlying httpx client. Every other provider accepts `timeout` directly.
_OLLAMA_PROVIDER = "ollama"

# The env var each provider's own SDK reads credentials from by default — used only to
# answer "is this provider configured" for /health, since construction alone doesn't
# reliably tell us: ChatOpenAI raises if the key is missing, ChatAnthropic doesn't.
_CREDENTIAL_ENV_VAR_BY_MODEL_TYPE: dict[type[BaseChatModel], str] = {
    ChatOpenAI: "OPENAI_API_KEY",
    ChatAnthropic: "ANTHROPIC_API_KEY",
}


def build_chat_model(config: RAGConfig, llm_settings: LLMSettings, *, timeout: float | None = None) -> BaseChatModel:
    """Build the chat model selected by ``config``/``llm_settings``.

    Args:
        config: Source of the provider/model selection and output-length cap
            (``llm_provider``, ``llm_model_name``, ``max_tokens``).
        llm_settings: Source of the ``api_base``/``api_key`` overrides (``TAPIO_LLM_API_BASE``/
            ``TAPIO_LLM_API_KEY``) — a remote/non-default Ollama server for ``"ollama"``, or
            Scaleway and other OpenAI-compatible endpoints with ``TAPIO_LLM_PROVIDER=openai``.
        timeout: Optional request timeout in seconds, baked into this instance at
            construction (LangChain's chat models don't support a per-call override).
            ``None`` waits indefinitely, matching each provider's own client default.

    Returns:
        A configured ``BaseChatModel``, ready for ``.invoke()``/``.stream()``.
    """
    _reject_cleartext_credentials(config, llm_settings)

    max_tokens_kwarg = _MAX_TOKENS_KWARG_BY_PROVIDER.get(config.llm_provider, "max_tokens")
    kwargs: dict[str, Any] = {
        "model_provider": config.llm_provider,
        "temperature": 0.7,
        "base_url": llm_settings.api_base,
        "api_key": llm_settings.api_key.get_secret_value() if llm_settings.api_key else None,
        max_tokens_kwarg: config.max_tokens,
    }
    if timeout is not None:
        if config.llm_provider == _OLLAMA_PROVIDER:
            kwargs["client_kwargs"] = {"timeout": timeout}
        else:
            kwargs["timeout"] = timeout
    return init_chat_model(config.llm_model_name, **kwargs)


def _reject_cleartext_credentials(config: RAGConfig, llm_settings: LLMSettings) -> None:
    """Refuse a non-loopback ``http://`` API base once a credential would cross it (CWE-319).

    A deployer who mistypes ``https://`` as ``http://`` for a genuinely remote endpoint
    (Scaleway, a self-hosted OpenAI-compatible proxy, a remote Ollama server) would
    otherwise send the API key and every prompt in cleartext. Loopback HTTP — a local dev
    proxy, or Ollama on the same host — carries no such risk and is left alone. A cloud
    provider's own SDK always sends *some* credential, explicit or from its own env var
    fallback, so this applies to it unconditionally; for Ollama, it only applies once an
    explicit ``TAPIO_LLM_API_KEY`` puts a credential in play.

    Args:
        config: Source of the provider selection.
        llm_settings: Source of ``api_base``/``api_key``.

    Raises:
        ValueError: If a credential would be sent to a non-loopback endpoint over plain HTTP.
    """
    api_base = llm_settings.api_base
    if api_base is None:
        return

    parsed = urlparse(api_base)
    if parsed.scheme != "http" or parsed.hostname in _LOOPBACK_HOSTS:
        return

    sends_credential = llm_settings.api_key is not None or config.llm_provider != _OLLAMA_PROVIDER
    if not sends_credential:
        return

    msg = (
        f"TAPIO_LLM_API_BASE={api_base!r} uses http:// against a non-loopback host, which "
        "would send API credentials in cleartext. Use https://, or point at localhost/127.0.0.1."
    )
    raise ValueError(msg)


def check_model_availability(model: BaseChatModel) -> bool:
    """Check whether ``model``'s provider is reachable and correctly configured.

    For Ollama, this makes a real (cheap) call to confirm the server is running and the
    configured model is pulled — the same check ``LLMService`` made before #9. For a
    cloud provider, a live call would cost money on every ``/health`` poll, so this only
    confirms credentials are present (via the provider's standard env var, or an explicit
    ``TAPIO_LLM_API_KEY``), not that they're valid.

    Args:
        model: The chat model to check, as returned by ``build_chat_model``.

    Returns:
        bool: True if the provider appears ready to serve requests.
    """
    if isinstance(model, ChatOllama):
        return _check_ollama_availability(model.model or "")

    env_var = next(
        (var for model_type, var in _CREDENTIAL_ENV_VAR_BY_MODEL_TYPE.items() if isinstance(model, model_type)),
        None,
    )
    if env_var is None:
        return True
    if os.environ.get(env_var):
        return True

    logger.warning("%s is not set and no TAPIO_LLM_API_KEY override is configured", env_var)
    return LLMSettings().api_key is not None


def _check_ollama_availability(model_name: str) -> bool:
    """Check if Ollama is running and has ``model_name`` pulled.

    A model name, including its tag, must match exactly. This prevents a configured
    model such as ``gemma4:latest`` from being treated as an installed variant such as
    ``gemma4:e4b``.

    Args:
        model_name: The configured Ollama model name.

    Returns:
        bool: True if the model is available, False otherwise.
    """
    try:
        models_response = ollama.list()

        if not hasattr(models_response, "models") or not models_response.models:
            logger.warning("No models found in Ollama")
            return False

        available_models = [model_obj.model for model_obj in models_response.models if model_obj.model]
        logger.info("Available Ollama models: %s", ", ".join(available_models))

        if model_name not in available_models:
            logger.warning(
                "%s model not found in Ollama. Please pull it with 'ollama pull %s'",
                model_name,
                model_name,
            )
            return False
        logger.info("Found exact matching model: %s", model_name)
    except Exception as e:
        logger.warning("Could not connect to Ollama: %s", e)
        logger.warning("Make sure Ollama is running")
        return False
    else:
        return True


def message_content_to_text(content: Any) -> str:
    """Convert a chat message's ``content`` into plain text.

    Handles both this app's own structured UI content blocks (fed in via
    ``build_messages``) and a model response's ``content``, which some providers
    return as a list of content blocks rather than a plain string.

    Args:
        content: A message's ``content`` value: plain text, or a list of content blocks.

    Returns:
        The text content.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_blocks: list[str] = []
        for block in content:
            if isinstance(block, str):
                text_blocks.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                text_blocks.append(block["text"])
        return "\n".join(text_blocks)

    return ""


def normalise_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep history roles while reducing structured UI content to text.

    Args:
        history: Prior conversation messages, in structured content-block form.

    Returns:
        The most recent messages with string roles and plain-text content.
    """
    return [
        {
            "role": str(message.get("role", "user")),
            "content": message_content_to_text(message.get("content")),
        }
        for message in history[-MAX_HISTORY_MESSAGES:]
    ]


def build_messages(
    prompt: str,
    system_prompt: str | None,
    history: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Build a role/content messages list a chat model's ``invoke``/``stream`` accepts.

    Args:
        prompt: The current user prompt.
        system_prompt: Optional system prompt to set context.
        history: Optional prior conversation turns (role/content dicts).

    Returns:
        Messages list ready to pass to ``BaseChatModel.invoke``/``.stream``.
    """
    messages: list[dict[str, Any]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if history:
        messages.extend(normalise_history(history))

    messages.append({"role": "user", "content": prompt})
    return messages


def invoke_text(model: BaseChatModel, messages: list[dict[str, Any]]) -> str:
    """Invoke ``model`` and return its response as plain text.

    Args:
        model: The chat model to call.
        messages: Messages built by ``build_messages``.

    Returns:
        The response text.
    """
    response = model.invoke(messages)
    return message_content_to_text(response.content)


def stream_text(model: BaseChatModel, messages: list[dict[str, Any]]) -> Generator[str]:
    """Stream ``model``'s response, yielding plain-text chunks.

    Args:
        model: The chat model to call.
        messages: Messages built by ``build_messages``.

    Yields:
        Non-empty text chunks as they arrive.
    """
    for chunk in model.stream(messages):
        text = message_content_to_text(chunk.content)
        if text:
            yield text
