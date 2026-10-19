"""Tests for GET /health."""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.config.config_models import RAGConfig
from app.config.llm_settings import LLMSettings
from app.dependencies import get_orchestrator
from app.main import app
from app.services.chat_model import build_chat_model
from app.services.rag_orchestrator import RAGOrchestrator


def test_health_reports_model_availability(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"model_available": True, "models": {"default": True}}


def test_health_reports_a_guardrail_override_without_a_credential_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A guardrail override on a provider with no key must turn /health red and say which role.

    The guardrail fails open on infra errors (a 401 included), so without this a missing
    ANTHROPIC_API_KEY would silently disable every guardrail check while generation, on the
    default Ollama model, keeps working.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = RAGConfig(
        llm_provider="ollama",
        llm_model_name="gemma4:latest",
        llm_model_overrides={"guardrail": "anthropic:claude-haiku-4-5"},
    )
    # The default provider's key must not count for a guardrail override on another provider.
    llm_settings = LLMSettings(api_key="ollama-proxy-key")
    orchestrator = RAGOrchestrator(
        doc_retrieval_service=Mock(),
        llm_service=build_chat_model(config, llm_settings),
        guardrail_model=build_chat_model(config, llm_settings, role="guardrail"),
    )
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    try:
        with patch("app.services.chat_model._check_ollama_availability", return_value=True):
            response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"model_available": False, "models": {"default": True, "guardrail": False}}
