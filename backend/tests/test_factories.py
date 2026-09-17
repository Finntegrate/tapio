"""Tests for RAGOrchestratorFactory's LLM provider selection (#9)."""

from app.config.config_models import RAGConfig
from app.factories import RAGOrchestratorFactory
from app.services.llm import LiteLLMProvider, OllamaProvider


def test_create_llm_provider_defaults_to_ollama() -> None:
    """With no provider override, the factory builds an OllamaProvider."""
    factory = RAGOrchestratorFactory(RAGConfig(llm_provider="ollama", llm_model_name="gemma4:latest"))

    provider = factory.create_llm_provider()

    assert isinstance(provider, OllamaProvider)
    assert provider.model_name == "gemma4:latest"


def test_create_llm_provider_selects_litellm() -> None:
    """Setting llm_provider to 'litellm' builds a LiteLLMProvider instead."""
    factory = RAGOrchestratorFactory(
        RAGConfig(llm_provider="litellm", llm_model_name="openai/gpt-4o-mini", max_tokens=512),
    )

    provider = factory.create_llm_provider()

    assert isinstance(provider, LiteLLMProvider)
    assert provider.model_name == "openai/gpt-4o-mini"
    assert provider.max_tokens == 512


def test_create_llm_provider_passes_api_base_and_key_to_litellm(monkeypatch) -> None:
    """TAPIO_LLM_API_BASE/TAPIO_LLM_API_KEY reach the LiteLLMProvider (e.g. for Scaleway)."""
    monkeypatch.setenv("TAPIO_LLM_API_BASE", "https://api.scaleway.ai/v1")
    monkeypatch.setenv("TAPIO_LLM_API_KEY", "secret-key")

    factory = RAGOrchestratorFactory(RAGConfig(llm_provider="litellm", llm_model_name="openai/llama-3.1-8b-instruct"))
    provider = factory.create_llm_provider()

    assert isinstance(provider, LiteLLMProvider)
    assert provider.api_base == "https://api.scaleway.ai/v1"
    assert provider.api_key == "secret-key"
