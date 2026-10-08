"""Tests for LLM provider/model env-var configuration (#9)."""

import pytest
from pydantic import ValidationError

from app.config.config_models import RAGConfig
from app.config.llm_settings import LLMSettings


def test_llm_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no env vars set, LLMSettings falls back to the local Ollama default."""
    for var in ("TAPIO_LLM_PROVIDER", "TAPIO_LLM_MODEL", "TAPIO_LLM_API_BASE", "TAPIO_LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)

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


def test_llm_settings_parses_model_overrides_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """TAPIO_LLM_MODEL_OVERRIDES is a JSON object, and RAGConfig picks it up (#139)."""
    monkeypatch.setenv(
        "TAPIO_LLM_MODEL_OVERRIDES",
        '{"sampo": "anthropic:claude-haiku-4-5", "guardrail": "gemma4:e2b"}',
    )

    assert RAGConfig().llm_model_overrides == {"sampo": "anthropic:claude-haiku-4-5", "guardrail": "gemma4:e2b"}


def test_llm_settings_model_overrides_default_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAPIO_LLM_MODEL_OVERRIDES", raising=False)

    assert LLMSettings().model_overrides == {}


def test_llm_settings_rejects_unknown_override_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mistyped guide id fails at startup instead of silently using the default model."""
    monkeypatch.setenv("TAPIO_LLM_MODEL_OVERRIDES", '{"samp": "gpt-4o-mini"}')

    with pytest.raises(ValidationError, match="samp"):
        LLMSettings()
