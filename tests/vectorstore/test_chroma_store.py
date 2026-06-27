"""Tests for the ChromaDB vector store abstraction."""

from unittest.mock import Mock, patch

import pytest
from langchain_core.documents import Document

from tapio.vectorstore.chroma_store import ChromaStore


class TestChromaStore:
    """Tests for the ChromaStore class."""

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_init(self, mock_chroma, mock_embeddings):
        """Test initialization of the ChromaStore."""
        # Initialize ChromaStore with injected embeddings
        _ = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
            persist_directory="test_dir",
        )

        # Check if vector_db was initialized correctly
        mock_chroma.assert_called_once_with(
            collection_name="test_collection",
            embedding_function=mock_embeddings,
            persist_directory="test_dir",
        )

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_add_document_with_content(self, mock_chroma, mock_embeddings):
        """Test adding a document with content in metadata."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_chroma.return_value = mock_vector_db

        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test adding document with content in metadata
        metadata = {"content": "Test document content"}
        store.add_document(document_id="test_doc_1", metadata=metadata)

        # Check if vector_db.add_texts was called with correct arguments
        mock_vector_db.add_texts.assert_called_once_with(
            texts=["Test document content"],
            metadatas=[metadata],
            ids=["test_doc_1"],
        )

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_add_document_alternate_content_fields(self, mock_chroma, mock_embeddings):
        """Test adding a document with content in alternate metadata fields."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_chroma.return_value = mock_vector_db

        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test with different content field names
        for field in ["text", "body", "page_content", "full_text"]:
            mock_vector_db.reset_mock()
            metadata = {field: f"Content in {field} field"}
            store.add_document(document_id=f"test_doc_{field}", metadata=metadata)

            # Check if vector_db.add_texts was called with correct arguments
            mock_vector_db.add_texts.assert_called_once_with(
                texts=[f"Content in {field} field"],
                metadatas=[metadata],
                ids=[f"test_doc_{field}"],
            )

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_add_document_no_content(self, mock_chroma, mock_embeddings):
        """Test adding a document with no content in metadata."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_chroma.return_value = mock_vector_db

        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test adding document with no content in metadata
        metadata = {"other_field": "Other value"}
        store.add_document(document_id="test_doc_empty", metadata=metadata)

        # Check if empty document message was used
        mock_vector_db.add_texts.assert_called_once_with(
            texts=["Empty document: test_doc_empty"],
            metadatas=[metadata],
            ids=["test_doc_empty"],
        )

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_add_document_exception(self, mock_chroma, mock_embeddings):
        """Test handling exceptions when adding a document."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_vector_db.add_texts.side_effect = Exception("Test error")
        mock_chroma.return_value = mock_vector_db

        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test adding document with exception
        metadata = {"content": "Test document content"}
        with pytest.raises(Exception, match="Test error"):
            store.add_document(document_id="test_doc", metadata=metadata)

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_query(self, mock_chroma, mock_embeddings):
        """Test querying the vector store by text."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_doc1 = Mock()
        mock_doc1.metadata = {}
        mock_doc2 = Mock()
        mock_doc2.metadata = {"source_url": "https://example.com/doc2"}
        mock_vector_db.similarity_search.return_value = [mock_doc1, mock_doc2]
        mock_chroma.return_value = mock_vector_db

        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test query
        results = store.query(query_text="test query", n_results=2)

        # Check if similarity_search was called with correct arguments
        mock_vector_db.similarity_search.assert_called_once_with(
            query="test query",
            k=2,
        )

        # Check if citation URL was added
        assert results == [mock_doc1, mock_doc2]
        assert "citation_url" in mock_doc2.metadata
        assert mock_doc2.metadata["citation_url"] == "https://example.com/doc2"

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_query_exception(self, mock_chroma, mock_embeddings):
        """Test handling exceptions when querying the vector store."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_vector_db.similarity_search.side_effect = Exception("Test error")
        mock_chroma.return_value = mock_vector_db

        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test query with exception
        results = store.query(query_text="test query")

        # Check if empty list was returned
        assert results == []

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_query_with_embedding(self, mock_chroma, mock_embeddings):
        """Test querying the vector store with embedding."""
        # Set up mocks
        mock_doc = Document(page_content="Test content", metadata={"source_url": "https://example.com/doc"})
        mock_vector_db = Mock()
        mock_vector_db.similarity_search_by_vector_with_relevance_scores.return_value = [(mock_doc, 0.1)]
        mock_chroma.return_value = mock_vector_db

        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test query with embedding
        embedding = [0.1, 0.2, 0.3]
        results = store.query_with_embedding(embedding=embedding, n_results=3)

        # Check if the public similarity search API was called with correct arguments
        mock_vector_db.similarity_search_by_vector_with_relevance_scores.assert_called_once_with(
            embedding,
            k=3,
        )

        # Check if citation URL was added
        doc, score = results[0]
        assert doc.metadata["citation_url"] == "https://example.com/doc"
        assert score == pytest.approx(0.1)

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_get_document(self, mock_chroma, mock_embeddings):
        """Test getting a document by ID."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_vector_db.get.return_value = {
            "documents": ["Test content"],
            "metadatas": [{"url": "https://example.com/doc"}],
        }
        mock_chroma.return_value = mock_vector_db

        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test get document
        result = store.get_document(document_id="test_doc")

        # Check if the public get API was called with correct arguments
        mock_vector_db.get.assert_called_once_with(
            ids=["test_doc"],
            include=["documents", "metadatas"],
        )

        # Check if citation URL was added
        assert "citation_url" in result["metadatas"][0]
        assert result["metadatas"][0]["citation_url"] == "https://example.com/doc"

    @patch("tapio.vectorstore.chroma_store.Chroma")
    def test_enhance_document_with_citation(self, mock_chroma, mock_embeddings):
        """Test enhancing a document with citation information."""
        # Initialize ChromaStore with injected embeddings
        store = ChromaStore(
            collection_name="test_collection",
            embeddings=mock_embeddings,
        )

        # Test with source_url
        doc1 = Mock()
        doc1.metadata = {"source_url": "https://example.com/doc1"}
        store._enhance_document_with_citation(doc1)
        assert doc1.metadata["citation_url"] == "https://example.com/doc1"

        # Test with url
        doc2 = Mock()
        doc2.metadata = {"url": "https://example.com/doc2"}
        store._enhance_document_with_citation(doc2)
        assert doc2.metadata["citation_url"] == "https://example.com/doc2"

        # Test with neither
        doc3 = Mock()
        doc3.metadata = {"other_field": "value"}
        store._enhance_document_with_citation(doc3)
        assert "citation_url" not in doc3.metadata

        # Test with no metadata attribute
        doc4 = Mock(spec=[])  # No metadata attribute
        store._enhance_document_with_citation(doc4)
        assert not hasattr(doc4, "metadata")
