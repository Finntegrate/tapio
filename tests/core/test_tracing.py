"""Tests for LangSmith tracing utilities (metadata extraction)."""

from unittest import mock

import pytest

from tapio.core.tracing import extract_document_metadata, trace_retrieval_metadata


class TestExtractDocumentMetadata:
    """Tests for ``extract_document_metadata``."""

    def test_empty_documents(self):
        assert extract_document_metadata([]) == []

    def test_document_without_metadata_attribute(self):
        doc = mock.MagicMock(spec=[])  # no metadata at all
        assert extract_document_metadata([doc]) == [{}]

    def test_document_with_non_dict_metadata(self):
        doc = mock.MagicMock()
        doc.metadata = "not_a_dict"
        assert extract_document_metadata([doc]) == [{}]

    def test_extracts_all_key_fields(self):
        doc = mock.MagicMock()
        doc.metadata = {
            "source_id": "doc-123",
            "source_url": "https://example.com/page",
            "citation_url": "https://example.com/page",
            "title": "Test Document",
            "chunk_index": 0,
            "total_chunks": 3,
            "file_name": "test.md",
            "source_path": "/data/test.md",
        }
        doc.page_content = "This is the document content."
        result = extract_document_metadata([doc])
        assert len(result) == 1
        entry = result[0]
        assert entry["source_id"] == "doc-123"
        assert entry["source_url"] == "https://example.com/page"
        assert entry["citation_url"] == "https://example.com/page"
        assert entry["title"] == "Test Document"
        assert entry["chunk_index"] == 0
        assert entry["total_chunks"] == 3
        assert entry["file_name"] == "test.md"
        assert entry["content_preview"] == "This is the document content."

    def test_falls_back_to_url_when_source_url_missing(self):
        doc = mock.MagicMock()
        doc.metadata = {
            "url": "https://example.com/page",
            "title": "Fallback Test",
        }
        result = extract_document_metadata([doc])
        assert result[0]["source_url"] == "https://example.com/page"

    def test_extra_metadata_included_separately(self):
        doc = mock.MagicMock()
        doc.metadata = {
            "title": "Extra Test",
            "source_url": "https://example.com",
            "author": "Test Author",
            "category": "immigration",
            "language": "fi",
        }
        result = extract_document_metadata([doc])
        extra = result[0].get("extra_metadata", {})
        assert extra["author"] == "Test Author"
        assert extra["category"] == "immigration"
        assert extra["language"] == "fi"

    def test_content_preview_truncated(self):
        doc = mock.MagicMock()
        doc.metadata = {"title": "Long Doc"}
        doc.page_content = "A" * 1000
        result = extract_document_metadata([doc])
        assert len(result[0]["content_preview"]) == 503  # 500 + "..."
        assert result[0]["content_preview"].endswith("...")

    def test_content_preview_empty_when_no_page_content(self):
        doc = mock.MagicMock()
        doc.metadata = {"title": "No Content"}
        result = extract_document_metadata([doc])
        assert result[0]["content_preview"] == ""

    def test_multiple_documents(self):
        docs = []
        for i in range(3):
            doc = mock.MagicMock()
            doc.metadata = {
                "chunk_index": i,
                "total_chunks": 3,
                "title": f"Doc {i}",
                "source_url": f"https://example.com/{i}",
            }
            doc.page_content = f"Content {i}"
            docs.append(doc)

        result = extract_document_metadata(docs)
        assert len(result) == 3
        for i, entry in enumerate(result):
            assert entry["chunk_index"] == i
            assert entry["title"] == f"Doc {i}"
            assert entry["source_url"] == f"https://example.com/{i}"
            assert entry["content_preview"] == f"Content {i}"

    def test_no_extra_when_only_known_keys(self):
        doc = mock.MagicMock()
        doc.metadata = {
            "source_id": "test",
            "source_url": "https://example.com",
            "url": "https://example.com",
            "citation_url": "https://example.com",
            "title": "Test",
            "chunk_index": 0,
            "total_chunks": 1,
            "file_name": "test.md",
            "source_path": "/test.md",
        }
        doc.page_content = "Some content."
        result = extract_document_metadata([doc])
        assert "extra_metadata" not in result[0]


class TestTraceRetrievalMetadata:
    """Tests for ``trace_retrieval_metadata``."""

    def test_delegates_to_extract(self):
        doc = mock.MagicMock()
        doc.metadata = {
            "source_id": "test",
            "title": "Trace Test",
        }
        result = trace_retrieval_metadata([doc])
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["source_id"] == "test"
        assert result[0]["title"] == "Trace Test"

    def test_empty_list(self):
        assert trace_retrieval_metadata([]) == []
