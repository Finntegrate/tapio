"""Shared fixtures for backend API tests."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from tapio.agents.router import AgentRouter

from tapio_backend.dependencies import get_agent_router, get_orchestrator
from tapio_backend.main import app


@pytest.fixture
def mock_rag_orchestrator() -> Mock:
    """Fake RAGOrchestrator whose query_stream returns a finite token stream."""
    orchestrator = Mock()
    mock_doc = Mock()
    mock_doc.page_content = "Test document content"
    mock_doc.metadata = {"source_url": "https://example.com", "title": "Example source"}

    orchestrator.query_stream.return_value = (iter(["Mocked ", "response"]), [mock_doc])
    orchestrator.check_model_availability.return_value = True
    return orchestrator


@pytest.fixture
def fake_agent_router() -> AgentRouter:
    """Real AgentRouter — pure and deterministic, no need to fake it."""
    return AgentRouter()


@pytest.fixture
def client(mock_rag_orchestrator: Mock, fake_agent_router: AgentRouter) -> Iterator[TestClient]:
    """TestClient with the orchestrator/router dependencies overridden.

    Deliberately not entered as a context manager, so the real lifespan
    (which builds a real RAGOrchestrator against Ollama/Chroma) never runs
    during tests.
    """
    app.dependency_overrides[get_orchestrator] = lambda: mock_rag_orchestrator
    app.dependency_overrides[get_agent_router] = lambda: fake_agent_router
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
