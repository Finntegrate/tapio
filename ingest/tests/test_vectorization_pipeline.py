"""Integration tests for the vectorization pipeline.

Tests the complete flow from markdown files to vector storage.
"""

import pytest
from langchain_chroma import Chroma  # type: ignore[import-not-found]
from langchain_text_splitters import (
    MarkdownTextSplitter,  # type: ignore[import-not-found]
)

from tapio_ingest.vectorstore.vectorizer import MarkdownVectorizer


@pytest.mark.integration
def test_markdown_vectorization_pipeline(tmp_path, tmp_chroma_db, mock_embeddings):
    """Test complete vectorization from markdown files to ChromaDB.

    This test:
    1. Creates test markdown files
    2. Creates vectorizer with real components
    3. Processes files
    4. Verifies documents are stored in vector database
    """
    # Create test markdown files
    test_content_dir = tmp_path / "content" / "test_site" / "parsed"
    test_content_dir.mkdir(parents=True)

    # Create test markdown file with frontmatter
    test_md = test_content_dir / "test_doc.md"
    test_md.write_text("""---
title: Test Document
source_url: https://example.com/test
---

# Test Document

This is a test document about residence permits in Finland.

## Requirements

You need a valid passport and proof of income.

## Processing Time

The processing time is typically 4-6 months.
""")

    # Create another test file
    test_md2 = test_content_dir / "test_doc2.md"
    test_md2.write_text("""---
title: Work Permits
source_url: https://example.com/work
---

# Work Permits

Work permits require a job offer from a Finnish employer.
""")

    # Create Chroma instance
    vector_db = Chroma(
        collection_name="test_vectorize",
        embedding_function=mock_embeddings,
        persist_directory=tmp_chroma_db,
    )

    # Create text splitter
    text_splitter = MarkdownTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )

    # Create vectorizer
    vectorizer = MarkdownVectorizer(
        vector_db=vector_db,
        text_splitter=text_splitter,
    )

    # Process directory
    count = vectorizer.process_directory(
        input_dir=str(test_content_dir.parent.parent),  # Process from content dir
        site_filter="test_site",
        batch_size=10,
    )

    # Verify files were processed
    assert count == 2

    # Verify documents are in the database (query returns results)
    results = vector_db.similarity_search("residence permits", k=5)
    assert len(results) > 0


@pytest.mark.integration
def test_vectorizer_handles_empty_directory(tmp_path, tmp_chroma_db, mock_embeddings):
    """Test that vectorizer handles empty directories gracefully."""
    # Create empty directory
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    # Create Chroma instance
    vector_db = Chroma(
        collection_name="test_empty",
        embedding_function=mock_embeddings,
        persist_directory=tmp_chroma_db,
    )

    # Create text splitter
    text_splitter = MarkdownTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )

    # Create vectorizer
    vectorizer = MarkdownVectorizer(
        vector_db=vector_db,
        text_splitter=text_splitter,
    )

    # Process empty directory
    count = vectorizer.process_directory(
        input_dir=str(empty_dir),
        batch_size=10,
    )

    # Verify no files were processed
    assert count == 0
