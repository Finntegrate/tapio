"""Tests for RAGOrchestratorFactory's chat model selection (#9, #139)."""

from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.config.config_models import RAGConfig
from app.factories import RAGOrchestratorFactory


def test_create_chat_model_defaults_to_ollama() -> None:
    """With no provider override, the factory builds a ChatOllama."""
    factory = RAGOrchestratorFactory(RAGConfig(llm_provider="ollama", llm_model_name="gemma4:latest"))

    model = factory.create_chat_model()

    assert isinstance(model, ChatOllama)
    assert model.model == "gemma4:latest"


def test_create_chat_model_selects_openai(monkeypatch) -> None:
    """Setting llm_provider to 'openai' builds a ChatOpenAI instead."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    factory = RAGOrchestratorFactory(
        RAGConfig(llm_provider="openai", llm_model_name="gpt-4o-mini", max_tokens=512),
    )

    model = factory.create_chat_model()

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-4o-mini"
    assert model.max_tokens == 512


def test_create_chat_model_selects_anthropic() -> None:
    """Setting llm_provider to 'anthropic' builds a ChatAnthropic."""
    factory = RAGOrchestratorFactory(
        RAGConfig(llm_provider="anthropic", llm_model_name="claude-3-5-haiku-20241022"),
    )

    model = factory.create_chat_model()

    assert isinstance(model, ChatAnthropic)
    assert model.model == "claude-3-5-haiku-20241022"


def test_create_chat_model_passes_api_base_and_key_for_scaleway(monkeypatch) -> None:
    """TAPIO_LLM_API_BASE/TAPIO_LLM_API_KEY reach the model (e.g. for Scaleway's OpenAI-compatible endpoint)."""
    monkeypatch.setenv("TAPIO_LLM_API_BASE", "https://api.scaleway.ai/v1")
    monkeypatch.setenv("TAPIO_LLM_API_KEY", "secret-key")

    factory = RAGOrchestratorFactory(RAGConfig(llm_provider="openai", llm_model_name="llama-3.1-8b-instruct"))
    model = factory.create_chat_model()

    assert isinstance(model, ChatOpenAI)
    assert str(model.openai_api_base) == "https://api.scaleway.ai/v1"
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == "secret-key"


def test_create_agent_chat_models_builds_one_model_per_overridden_guide(monkeypatch) -> None:
    """Only guides with an override get their own model; stages like the guardrail don't."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    factory = RAGOrchestratorFactory(
        RAGConfig(
            llm_provider="ollama",
            llm_model_name="gemma4:latest",
            llm_model_overrides={"sampo": "anthropic:claude-haiku-4-5", "guardrail": "gemma4:e2b"},
        ),
    )

    models = factory.create_agent_chat_models()

    assert set(models) == {"sampo"}
    assert isinstance(models["sampo"], ChatAnthropic)


def test_create_agent_chat_models_is_empty_without_overrides() -> None:
    factory = RAGOrchestratorFactory(RAGConfig(llm_model_overrides={}))

    assert factory.create_agent_chat_models() == {}


def test_create_chat_model_honors_a_stage_override() -> None:
    factory = RAGOrchestratorFactory(
        RAGConfig(
            llm_provider="ollama", llm_model_name="gemma4:latest", llm_model_overrides={"guardrail": "gemma4:e2b"}
        ),
    )

    assert factory.create_chat_model(role="guardrail").model == "gemma4:e2b"
    assert factory.create_chat_model().model == "gemma4:latest"
