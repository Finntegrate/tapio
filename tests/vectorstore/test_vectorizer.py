"""Tests for the markdown vectorizer."""

from unittest.mock import Mock, call, patch

from tapio.vectorstore.vectorizer import MarkdownVectorizer


class TestMarkdownVectorizer:
    """Tests for the MarkdownVectorizer class."""

    def test_init(self):
        """Test initialization of the vectorizer."""
        # Create mocks
        mock_vector_db = Mock()
        mock_text_splitter = Mock()

        # Initialize vectorizer with dependency injection
        vectorizer = MarkdownVectorizer(
            vector_db=mock_vector_db,
            text_splitter=mock_text_splitter,
        )

        # Check if dependencies were stored
        assert vectorizer.vector_db == mock_vector_db
        assert vectorizer.text_splitter == mock_text_splitter

    @patch("tapio.vectorstore.vectorizer.find_markdown_files")
    def test_process_directory(self, mock_find_files):
        """Test processing a directory of markdown files."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_text_splitter = Mock()

        # Set up mock for find_markdown_files to return some test files
        test_files = [
            "test_dir/file1.md",
            "test_dir/file2.md",
            "test_dir/file3.md",
        ]
        mock_find_files.return_value = test_files

        # Initialize vectorizer with mocked _process_batch
        vectorizer = MarkdownVectorizer(
            vector_db=mock_vector_db,
            text_splitter=mock_text_splitter,
        )
        vectorizer._process_batch = Mock(return_value=2)  # 2 chunks per batch

        # Process directory
        processed_count = vectorizer.process_directory(
            input_dir="test_dir",
            site_filter="migri",
            batch_size=2,
        )

        # Verify find_markdown_files was called correctly
        mock_find_files.assert_called_once_with("test_dir", "migri")

        # Verify _process_batch was called correctly for each batch
        assert vectorizer._process_batch.call_count == 2
        vectorizer._process_batch.assert_has_calls(
            [
                call(["test_dir/file1.md", "test_dir/file2.md"]),
                call(["test_dir/file3.md"]),
            ],
        )

        # Verify correct number of files was returned
        assert processed_count == 3

    @patch("tapio.vectorstore.vectorizer.read_markdown_file")
    @patch("tapio.vectorstore.vectorizer.Document")
    def test_process_batch(
        self,
        mock_document_class,
        mock_read_file,
    ):
        """Test processing a batch of markdown files."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_text_splitter = Mock()

        # Set up read_markdown_file to return test data
        mock_read_file.side_effect = [
            ({"title": "Test 1"}, "Content 1"),
            ({"title": "Test 2"}, "Content 2"),
        ]

        # Set up Document
        mock_doc1 = Mock()
        mock_doc2 = Mock()
        mock_document_class.side_effect = [mock_doc1, mock_doc2]

        # Set up text splitter
        mock_chunk1 = Mock()
        mock_chunk1.metadata = {}
        mock_chunk2 = Mock()
        mock_chunk2.metadata = {}
        mock_chunk3 = Mock()
        mock_chunk3.metadata = {}
        mock_text_splitter.split_documents.side_effect = [
            [mock_chunk1, mock_chunk2],  # First document splits into 2 chunks
            [mock_chunk3],  # Second document splits into 1 chunk
        ]

        # Initialize vectorizer
        vectorizer = MarkdownVectorizer(
            vector_db=mock_vector_db,
            text_splitter=mock_text_splitter,
        )

        # Set up _prepare_metadata to return test metadata
        vectorizer._prepare_metadata = Mock(
            side_effect=[
                {"source_id": "file1", "title": "Test 1"},
                {"source_id": "file2", "title": "Test 2"},
            ],
        )

        # Process batch
        chunk_count = vectorizer._process_batch(
            [
                "test_dir/file1.md",
                "test_dir/file2.md",
            ],
        )

        # Verify read_markdown_file was called for each file
        mock_read_file.assert_has_calls(
            [
                call("test_dir/file1.md"),
                call("test_dir/file2.md"),
            ],
        )

        # Verify Document was created for each file
        mock_document_class.assert_has_calls(
            [
                call(
                    page_content="Content 1",
                    metadata={"source_id": "file1", "title": "Test 1"},
                ),
                call(
                    page_content="Content 2",
                    metadata={"source_id": "file2", "title": "Test 2"},
                ),
            ],
        )

        # Verify text splitter was called for each document
        mock_text_splitter.split_documents.assert_has_calls(
            [
                call([mock_doc1]),
                call([mock_doc2]),
            ],
        )

        # Verify chunk metadata was updated
        assert mock_chunk1.metadata["chunk_index"] == 0
        assert mock_chunk1.metadata["total_chunks"] == 2
        assert mock_chunk2.metadata["chunk_index"] == 1
        assert mock_chunk2.metadata["total_chunks"] == 2
        assert mock_chunk3.metadata["chunk_index"] == 0
        assert mock_chunk3.metadata["total_chunks"] == 1

        # Verify add_documents was called with all chunks
        mock_vector_db.add_documents.assert_called_once_with(
            [mock_chunk1, mock_chunk2, mock_chunk3],
        )

        # Verify correct number of chunks was returned
        assert chunk_count == 3

    @patch("tapio.vectorstore.vectorizer.read_markdown_file")
    @patch("tapio.vectorstore.vectorizer.Document")
    def test_process_file(
        self,
        mock_document_class,
        mock_read_file,
    ):
        """Test processing a single markdown file."""
        # Set up mocks
        mock_vector_db = Mock()
        mock_text_splitter = Mock()

        # Set up read_markdown_file to return test data
        mock_read_file.return_value = ({"title": "Test"}, "Content")

        # Set up Document
        mock_doc = Mock()
        mock_document_class.return_value = mock_doc

        # Set up text splitter
        mock_chunk1 = Mock()
        mock_chunk1.metadata = {}
        mock_chunk2 = Mock()
        mock_chunk2.metadata = {}
        mock_text_splitter.split_documents.return_value = [mock_chunk1, mock_chunk2]

        # Initialize vectorizer with dependency injection
        vectorizer = MarkdownVectorizer(
            vector_db=mock_vector_db,
            text_splitter=mock_text_splitter,
        )

        # Set up _prepare_metadata to return test metadata
        test_metadata = {"source_id": "file", "title": "Test"}
        vectorizer._prepare_metadata = Mock(return_value=test_metadata)

        # Process file
        chunk_count = vectorizer.process_file("test_dir/file.md")

        # Verify read_markdown_file was called
        mock_read_file.assert_called_once_with("test_dir/file.md")

        # Verify Document was created
        mock_document_class.assert_called_once_with(
            page_content="Content",
            metadata=test_metadata,
        )

        # Verify text splitter was called
        mock_text_splitter.split_documents.assert_called_once_with([mock_doc])

        # Verify chunk metadata was updated
        assert mock_chunk1.metadata["chunk_index"] == 0
        assert mock_chunk1.metadata["total_chunks"] == 2
        assert mock_chunk2.metadata["chunk_index"] == 1
        assert mock_chunk2.metadata["total_chunks"] == 2

        # Verify add_documents was called
        mock_vector_db.add_documents.assert_called_once_with([mock_chunk1, mock_chunk2])

        # Verify correct number of chunks was returned
        assert chunk_count == 2

    def test_prepare_metadata(self):
        """Test preparing metadata for a document."""
        mock_vector_db = Mock()
        mock_text_splitter = Mock()

        # Initialize vectorizer with dependency injection
        vectorizer = MarkdownVectorizer(
            vector_db=mock_vector_db,
            text_splitter=mock_text_splitter,
        )

        # Test with source_url
        metadata = {
            "title": "Test Document",
            "source_url": "https://example.com/doc",
        }

        enriched = vectorizer._prepare_metadata(metadata, "test_dir/file.md")

        # Verify metadata was enriched correctly
        assert enriched["title"] == "Test Document"
        assert enriched["source_url"] == "https://example.com/doc"
        assert enriched["url"] == "https://example.com/doc"
        assert enriched["citation_url"] == "https://example.com/doc"
        assert enriched["source_id"] == "file"
        assert enriched["source_path"] == "test_dir/file.md"
        assert enriched["file_name"] == "file.md"

        # Test with url but no source_url
        metadata = {
            "title": "Test Document",
            "url": "https://example.com/doc",
        }

        enriched = vectorizer._prepare_metadata(metadata, "test_dir/file.md")

        # Verify metadata was enriched correctly
        assert enriched["title"] == "Test Document"
        assert enriched["url"] == "https://example.com/doc"
        assert enriched["source_url"] == "https://example.com/doc"
        assert enriched["citation_url"] == "https://example.com/doc"
