"""Configuration file for pytest."""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add the project root directory to the Python path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))


# ============================================================================
# Mock Fixtures for Unit Tests
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

    # embed_query returns a single embedding (copy to avoid mutation)
    embeddings.embed_query.side_effect = lambda _: dummy_embedding.copy()

    # embed_documents returns a list of embeddings (one per document)
    # Make it return the appropriate number based on input
    def embed_documents_mock(texts):
        return [dummy_embedding.copy() for _ in texts]

    embeddings.embed_documents.side_effect = embed_documents_mock
    return embeddings


@pytest.fixture
def mock_chroma_store():
    """Mock ChromaStore for unit tests."""
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

    # Create mock documents
    mock_doc = Mock()
    mock_doc.page_content = "Test document content"
    mock_doc.metadata = {"source": "test.md", "url": "https://example.com"}

    service.retrieve_documents.return_value = [mock_doc]
    service.format_documents_as_context.return_value = "Test document content"
    return service


@pytest.fixture
def mock_rag_orchestrator():
    """Mock RAGOrchestrator for unit tests."""
    orchestrator = Mock()

    # Create mock documents
    mock_doc = Mock()
    mock_doc.page_content = "Test document content"
    mock_doc.metadata = {"source": "test.md", "url": "https://example.com"}

    orchestrator.query.return_value = ("Mocked response", [mock_doc])
    orchestrator.query_stream.return_value = (iter(["Mocked ", "response"]), [mock_doc])
    orchestrator.check_model_availability.return_value = True
    orchestrator.format_documents_for_display.return_value = "**Source:** test.md"
    return orchestrator


@pytest.fixture
def tmp_chroma_db(tmp_path):
    """Temporary directory for ChromaDB in integration tests."""
    db_dir = tmp_path / "chroma_db"
    db_dir.mkdir()
    return str(db_dir)


# ============================================================================
# Integration Test Markers
# ============================================================================


def pytest_configure(config):
    """Add custom markers for pytest."""
    config.addinivalue_line("markers", "integration: mark test as integration test (uses real embeddings, slower)")
