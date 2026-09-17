"""The ``LLMProvider`` interface and message-building helpers shared by every implementation.

Introduced in #9 to make the LLM backend swappable via configuration
(``TAPIO_LLM_PROVIDER``/``TAPIO_LLM_MODEL``, see ``app.config.llm_settings``)
rather than hardcoded to one vendor's SDK. Callers throughout the app
(``RAGOrchestrator``, the graph's generation node, the guardrail response
builder) depend on this interface, not on a concrete provider, so a new
provider only has to be implemented here and selected in
``RAGOrchestratorFactory`` — no other call site changes.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Cap on prior turns included as context, to avoid overflowing the model's context window.
MAX_HISTORY_MESSAGES = 10


def message_content_to_text(content: Any) -> str:
    """Convert a structured chat message value into plain text.

    Args:
        content: A message value, which may be plain text or a list of content blocks.

    Returns:
        The text content suitable for a provider chat message.
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
    """Build an OpenAI/Ollama-style chat messages list from a prompt, system prompt, and history.

    Both providers' underlying clients (``ollama``'s chat API and LiteLLM's
    OpenAI-compatible ``completion``) accept this same ``{"role", "content"}``
    message shape, so this builder is shared rather than duplicated per provider.

    Args:
        prompt: The current user prompt.
        system_prompt: Optional system prompt to set context.
        history: Optional prior conversation turns (role/content dicts).

    Returns:
        Messages list ready to pass to a provider's chat call.
    """
    messages: list[dict[str, Any]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if history:
        messages.extend(normalise_history(history))

    messages.append({"role": "user", "content": prompt})
    return messages


class LLMProvider(ABC):
    """A swappable LLM backend: local (Ollama) or cloud/OpenAI-compatible (LiteLLM).

    Concrete providers set ``self.model_name`` in ``__init__``; ``get_model_name``
    below relies on it.
    """

    model_name: str

    @abstractmethod
    def generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, Any]] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: The prompt to generate a response for.
            system_prompt: Optional system prompt to set context.
            history: Optional prior conversation turns to include as context.
            timeout: Optional request timeout in seconds, enforced by the underlying
                provider client itself. ``None`` waits indefinitely.

        Returns:
            The generated response, or a safe error string if generation failed.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_response_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> Generator[str]:
        """Generate a streaming response from the LLM.

        Args:
            prompt: The prompt to generate a response for.
            system_prompt: Optional system prompt to set context.
            history: Optional prior conversation turns to include as context.

        Yields:
            Chunks of the generated response.
        """
        raise NotImplementedError

    @abstractmethod
    def check_model_availability(self) -> bool:
        """Check whether this provider is reachable and correctly configured.

        Returns:
            True if the provider is ready to serve requests.
        """
        raise NotImplementedError

    def get_model_name(self) -> str:
        """Get the name of the model being used.

        Returns:
            The model name.
        """
        return self.model_name

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        system_prompt: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> BaseModel:
        """Generate a response constrained to a Pydantic schema.

        This is the structured-output hook the interface commits to (#9); the
        schema-in/validated-instance-out contract itself, and provider
        implementations of it, land in #140. Until then, every provider
        raises ``NotImplementedError`` here.

        Args:
            prompt: The prompt to generate a response for.
            schema: The Pydantic model the response must conform to.
            system_prompt: Optional system prompt to set context.
            history: Optional prior conversation turns to include as context.

        Returns:
            A validated instance of ``schema``.

        Raises:
            NotImplementedError: Always, until #140 implements this per provider.
        """
        msg = f"{type(self).__name__} does not support structured output yet (see #140)."
        raise NotImplementedError(msg)
