"""Shared fixtures for backend tests: RAG/agent unit tests and the FastAPI API tests."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.agents.router import AgentRouter
from app.dependencies import get_agent_router, get_orchestrator
from app.main import app

# ============================================================================
# Mock fixtures for RAG/agent unit tests
# ============================================================================


@pytest.fixture
def mock_embeddings():
    """Mock HuggingFace embeddings for fast unit tests.

    Returns a mock with embed_query and embed_documents methods that return
    consistent dummy embeddings without loading a real model.
    """
    embeddings = Mock()
    # Typical embedding dimension for all-MiniLM-L6-v2 is 384
    dummy_embedding = [0.1] * 384

    embeddings.embed_query.side_effect = lambda _: dummy_embedding.copy()

    def embed_documents_mock(texts):
        return [dummy_embedding.copy() for _ in texts]

    embeddings.embed_documents.side_effect = embed_documents_mock
    return embeddings


@pytest.fixture
def mock_chroma_store():
    """Mock ChromaRetriever for unit tests."""
    store = Mock()
    store.query.return_value = []
    store.add_document.return_value = None
    store.add_documents.return_value = None
    return store


@pytest.fixture
def mock_llm_service():
    """Mock LLMService for unit tests."""
    service = Mock()
    service.generate_response.return_value = "Mocked LLM response"
    service.generate_response_stream.return_value = iter(["Mocked ", "streamed ", "response"])
    service.check_model_availability.return_value = True
    return service


@pytest.fixture
def mock_doc_retrieval_service():
    """Mock DocumentRetrievalService for unit tests."""
    service = Mock()

    mock_doc = Mock()
    mock_doc.page_content = "Test document content"
    mock_doc.metadata = {"source": "test.md", "url": "https://example.com"}

    service.retrieve_documents.return_value = [mock_doc]
    service.format_documents_as_context.return_value = "Test document content"
    return service


@pytest.fixture
def tmp_chroma_db(tmp_path):
    """Temporary directory for ChromaDB in integration tests."""
    db_dir = tmp_path / "chroma_db"
    db_dir.mkdir()
    return str(db_dir)


def pytest_configure(config):
    """Add custom markers for pytest."""
    config.addinivalue_line("markers", "integration: mark test as integration test (uses real embeddings, slower)")


# ============================================================================
# Fixtures for the FastAPI API tests
# ============================================================================


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
