"""Tests for LLM provider/model env-var configuration (#9)."""

import pytest

from app.config.config_models import RAGConfig
from app.config.llm_settings import LLMSettings


def test_llm_settings_defaults() -> None:
    """With no env vars set, LLMSettings falls back to the local Ollama default."""
    settings = LLMSettings()

    assert settings.provider == "ollama"
    assert settings.model == "gemma4:latest"
    assert settings.api_base is None
    assert settings.api_key is None


def test_llm_settings_reads_provider_and_model_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """TAPIO_LLM_PROVIDER and TAPIO_LLM_MODEL override the defaults."""
    monkeypatch.setenv("TAPIO_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TAPIO_LLM_MODEL", "gpt-4o-mini")

    settings = LLMSettings()

    assert settings.provider == "openai"
    assert settings.model == "gpt-4o-mini"


def test_llm_settings_reads_api_base_and_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """TAPIO_LLM_API_BASE and TAPIO_LLM_API_KEY are read for Scaleway-style endpoints."""
    monkeypatch.setenv("TAPIO_LLM_API_BASE", "https://api.scaleway.ai/v1")
    monkeypatch.setenv("TAPIO_LLM_API_KEY", "secret-key")

    settings = LLMSettings()

    assert settings.api_base == "https://api.scaleway.ai/v1"
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "secret-key"


def test_rag_config_defaults_pick_up_llm_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAGConfig's provider/model defaults track LLMSettings, not a fixed constant."""
    monkeypatch.setenv("TAPIO_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("TAPIO_LLM_MODEL", "claude-3-5-haiku-20241022")

    config = RAGConfig()

    assert config.llm_provider == "anthropic"
    assert config.llm_model_name == "claude-3-5-haiku-20241022"


def test_rag_config_explicit_llm_fields_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicitly passed llm_provider/llm_model_name wins over the env-derived default."""
    monkeypatch.setenv("TAPIO_LLM_PROVIDER", "anthropic")

    config = RAGConfig(llm_provider="ollama", llm_model_name="gemma4:latest")

    assert config.llm_provider == "ollama"
    assert config.llm_model_name == "gemma4:latest"
