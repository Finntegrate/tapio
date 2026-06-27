"""Tests for the document retrieval service."""

from unittest import mock

import pytest

from tapio.services.document_retrieval_service import DocumentRetrievalService


@pytest.fixture
def doc_retrieval_service(mock_chroma_store):
    """Create a document retrieval service with mocked dependencies for testing."""
    # Create DocumentRetrievalService with injected mock ChromaStore
    return DocumentRetrievalService(
        vector_store=mock_chroma_store,
        num_results=3,
    )


def test_document_retrieval_service_retrieves_documents(doc_retrieval_service):
    """Test that document retrieval service correctly retrieves documents."""
    # Mock vector store query to return some documents
    mock_doc1 = mock.MagicMock()
    mock_doc1.page_content = "First test document content"
    mock_doc1.metadata = {
        "title": "Doc 1",
        "source_url": "http://example.com/1",
    }

    mock_doc2 = mock.MagicMock()
    mock_doc2.page_content = "Second test document content"
    mock_doc2.metadata = {
        "title": "Doc 2",
        "source_url": "http://example.com/2",
    }

    doc_retrieval_service.vector_store.query.return_value = [
        mock_doc1,
        mock_doc2,
    ]

    # Call the method under test
    result = doc_retrieval_service.retrieve_documents("Test query")

    # Verify the vector store was called correctly
    doc_retrieval_service.vector_store.query.assert_called_once_with(
        query_text="Test query",
        n_results=3,
    )

    # Verify the results
    assert len(result) == 2
    assert result[0] == mock_doc1
    assert result[1] == mock_doc2


def test_document_retrieval_service_formats_context(doc_retrieval_service):
    """Test that document retrieval service correctly formats documents as context."""
    # Create mock documents
    mock_doc1 = mock.MagicMock()
    mock_doc1.page_content = "First document content"

    mock_doc2 = mock.MagicMock()
    mock_doc2.page_content = "Second document content"

    documents = [mock_doc1, mock_doc2]

    # Call the method under test
    context = doc_retrieval_service.format_documents_as_context(documents)

    # Verify the context is formatted correctly
    expected_context = "First document content\n\nSecond document content"
    assert context == expected_context


def test_document_retrieval_service_formats_display(doc_retrieval_service):
    """Test that document retrieval service correctly formats documents for display."""
    # Create mock documents
    mock_doc1 = mock.MagicMock()
    mock_doc1.page_content = "First document content"
    mock_doc1.metadata = {
        "title": "Document 1",
        "source_url": "http://example.com/1",
    }

    mock_doc2 = mock.MagicMock()
    mock_doc2.page_content = "Second document content"
    mock_doc2.metadata = {
        "title": "Document 2",
        "source_url": "http://example.com/2",
    }

    documents = [mock_doc1, mock_doc2]

    # Call the method under test
    display_text = doc_retrieval_service.format_documents_for_display(
        documents,
    )

    # Verify the display text includes titles, sources, and content
    assert "### Document 1" in display_text
    assert "**Source**: http://example.com/1" in display_text
    assert "First document content" in display_text
    assert "### Document 2" in display_text
    assert "**Source**: http://example.com/2" in display_text
    assert "Second document content" in display_text
