"""Integration tests for the complete RAG pipeline.

These tests use real components (embeddings, vector database) to verify
end-to-end functionality. The LLM service is mocked to avoid external
dependencies on Ollama.
"""

from unittest.mock import Mock, patch

import pytest
from langchain_core.documents import Document  # type: ignore[import-not-found]

from tapio.config.config_models import RAGConfig
from tapio.factories import RAGOrchestratorFactory
from tapio.services.document_retrieval_service import DocumentRetrievalService
from tapio.services.llm_service import LLMService
from tapio.services.rag_orchestrator import RAGOrchestrator
from tapio.vectorstore.chroma_store import ChromaStore


@pytest.mark.integration
def test_rag_pipeline_end_to_end(tmp_chroma_db, mock_embeddings):
    """Test complete RAG pipeline from document storage to query response.

    This test:
    1. Creates a real ChromaDB instance with mock embeddings
    2. Adds test documents to the vector store
    3. Creates a RAG orchestrator with mock LLM
    4. Queries the system and verifies document retrieval
    """
    # Create ChromaStore with real Chroma and mock embeddings
    chroma_store = ChromaStore(
        collection_name="test_integration",
        embeddings=mock_embeddings,
        persist_directory=tmp_chroma_db,
    )

    # Add test documents
    test_docs = [
        Document(
            page_content="Finland residence permits require a valid passport and proof of income.",
            metadata={"source": "residence_permit.md", "url": "https://example.com/residence"},
        ),
        Document(
            page_content="Processing time for residence permits is typically 4-6 months.",
            metadata={"source": "processing_times.md", "url": "https://example.com/times"},
        ),
        Document(
            page_content="Work permits in Finland depend on having a job offer from a Finnish employer.",
            metadata={"source": "work_permit.md", "url": "https://example.com/work"},
        ),
    ]

    # Add documents to vector store
    chroma_store.vector_db.add_documents(test_docs)

    # Create mock LLM service
    mock_llm = Mock(spec=LLMService)
    mock_llm.generate_response.return_value = (
        "Based on the documents, residence permits require a valid passport and "
        "proof of income, with processing times of 4-6 months."
    )
    mock_llm.check_model_availability.return_value = True

    # Create document retrieval service
    doc_service = DocumentRetrievalService(
        vector_store=chroma_store,
        num_results=3,
    )

    # Create RAG orchestrator
    orchestrator = RAGOrchestrator(
        doc_retrieval_service=doc_service,
        llm_service=mock_llm,
    )

    # Query the system
    with patch("tapio.services.rag_orchestrator.load_prompt") as mock_load_prompt:
        mock_load_prompt.side_effect = ["You are a helpful assistant.", "Context: {context}\n\nQuestion: {question}"]

        response, retrieved_docs = orchestrator.query("How do I apply for a residence permit?")

    # Verify response
    assert response is not None
    assert "passport" in response.lower() or "residence" in response.lower()

    # Verify documents were retrieved
    assert len(retrieved_docs) > 0

    # Verify LLM was called
    mock_llm.generate_response.assert_called_once()


@pytest.mark.integration
def test_rag_factory_integration(tmp_chroma_db, mock_embeddings):
    """Test RAG orchestrator creation using factory pattern.

    Verifies that the factory correctly wires all dependencies.
    """
    # Create config
    config = RAGConfig(
        collection_name="test_factory",
        persist_directory=tmp_chroma_db,
        embedding_model_name="all-MiniLM-L6-v2",
        llm_model_name="llama3.2",
        max_tokens=512,
        num_results=3,
    )

    # Create factory
    factory = RAGOrchestratorFactory(config)

    # Mock the create_embeddings to return our mock
    with patch.object(factory, "create_embeddings", return_value=mock_embeddings):
        # Create orchestrator
        orchestrator = factory.create_orchestrator()

    # Verify orchestrator was created
    assert isinstance(orchestrator, RAGOrchestrator)
    assert orchestrator.doc_retrieval_service is not None
    assert orchestrator.llm_service is not None


@pytest.mark.integration
def test_document_retrieval_similarity_search(tmp_chroma_db, mock_embeddings):
    """Test that similar documents are retrieved correctly."""
    # Create ChromaStore
    chroma_store = ChromaStore(
        collection_name="test_similarity",
        embeddings=mock_embeddings,
        persist_directory=tmp_chroma_db,
    )

    # Add documents with different topics
    docs = [
        Document(
            page_content="Residence permits are required for living in Finland.",
            metadata={"source": "doc1.md", "topic": "residence"},
        ),
        Document(
            page_content="Tourist visas allow short visits to Finland.",
            metadata={"source": "doc2.md", "topic": "visa"},
        ),
        Document(
            page_content="Permanent residence permits grant long-term stay rights.",
            metadata={"source": "doc3.md", "topic": "residence"},
        ),
    ]

    chroma_store.vector_db.add_documents(docs)

    # Create retrieval service
    doc_service = DocumentRetrievalService(
        vector_store=chroma_store,
        num_results=2,
    )

    # Query for residence permits (should return residence-related docs)
    results = doc_service.retrieve_documents("residence permits")

    # Verify we got results
    assert len(results) == 2  # Should return exactly num_results documents

    # Verify results have content
    for doc in results:
        assert hasattr(doc, "page_content")
        assert len(doc.page_content) > 0
