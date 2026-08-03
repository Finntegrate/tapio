"""Tests for the embedding utilities."""

from unittest.mock import Mock, patch

from tapio.utils.embedding_utils import EmbeddingGenerator


class TestEmbeddingGenerator:
    """Tests for the EmbeddingGenerator class."""

    @patch("tapio.utils.embedding_utils.SentenceTransformerEmbeddings")
    def test_init_default_model(self, mock_sentence_transformer):
        """Test initialization with default model name."""
        generator = EmbeddingGenerator()

        # Check if initialized with the correct default model
        mock_sentence_transformer.assert_called_once_with(model_name="all-MiniLM-L6-v2")
        assert generator.model_name == "all-MiniLM-L6-v2"

    @patch("tapio.utils.embedding_utils.SentenceTransformerEmbeddings")
    def test_init_custom_model(self, mock_sentence_transformer):
        """Test initialization with custom model name."""
        custom_model = "paraphrase-multilingual-MiniLM-L12-v2"
        generator = EmbeddingGenerator(model_name=custom_model)

        # Check if initialized with the custom model
        mock_sentence_transformer.assert_called_once_with(model_name=custom_model)
        assert generator.model_name == custom_model

    @patch("tapio.utils.embedding_utils.SentenceTransformerEmbeddings")
    def test_generate_embedding(self, mock_sentence_transformer):
        """Test generation of a single embedding."""
        # Mock the embed_query method to return a sample embedding
        mock_model = Mock()
        mock_model.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]
        mock_sentence_transformer.return_value = mock_model

        generator = EmbeddingGenerator()
        embedding = generator.generate("Test text")

        # Check if embed_query was called with the right text
        mock_model.embed_query.assert_called_once_with("Test text")
        # Check if the result matches the expected embedding
        assert embedding == [0.1, 0.2, 0.3, 0.4]

    @patch("tapio.utils.embedding_utils.SentenceTransformerEmbeddings")
    def test_generate_embedding_error(self, mock_sentence_transformer):
        """Test error handling during single embedding generation."""
        # Mock the embed_query method to raise an exception
        mock_model = Mock()
        mock_model.embed_query.side_effect = ValueError("Test error")
        mock_sentence_transformer.return_value = mock_model

        generator = EmbeddingGenerator()
        embedding = generator.generate("Test text")

        # Check if the error is handled and None is returned
        assert embedding is None

    @patch("tapio.utils.embedding_utils.SentenceTransformerEmbeddings")
    def test_generate_batch_embeddings(self, mock_sentence_transformer):
        """Test generation of batch embeddings."""
        # Mock the embed_documents method to return sample embeddings
        mock_model = Mock()
        mock_model.embed_documents.return_value = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ]
        mock_sentence_transformer.return_value = mock_model

        generator = EmbeddingGenerator()
        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = generator.generate_batch(texts)

        # Check if embed_documents was called with the right texts
        mock_model.embed_documents.assert_called_once_with(texts)
        # Check if the result matches the expected embeddings
        assert len(embeddings) == 3
        assert embeddings[0] == [0.1, 0.2, 0.3]
        assert embeddings[1] == [0.4, 0.5, 0.6]
        assert embeddings[2] == [0.7, 0.8, 0.9]

    @patch("tapio.utils.embedding_utils.SentenceTransformerEmbeddings")
    def test_generate_batch_embeddings_error(self, mock_sentence_transformer):
        """Test error handling during batch embedding generation."""
        # Mock the embed_documents method to raise an exception
        mock_model = Mock()
        mock_model.embed_documents.side_effect = ValueError("Test error")
        mock_sentence_transformer.return_value = mock_model

        generator = EmbeddingGenerator()
        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = generator.generate_batch(texts)

        # Check if the error is handled and a list of Nones with correct length is returned
        assert len(embeddings) == 3
        assert embeddings == [None, None, None]
