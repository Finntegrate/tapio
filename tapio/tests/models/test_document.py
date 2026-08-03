"""Tests for the Document model."""

from tapio.models.document import Document


class TestDocument:
    """Tests for the Document model."""

    def test_init(self):
        """Test initialization of the Document model."""
        url = "https://example.com/page"
        content = "This is the content"
        metadata = {"title": "Test Page", "author": "Test Author"}

        document = Document(url=url, content=content, metadata=metadata)

        assert document.url == url
        assert document.content == content
        assert document.metadata == metadata

    def test_to_dict(self):
        """Test converting the Document to a dictionary."""
        url = "https://example.com/page"
        content = "This is the content"
        metadata = {"title": "Test Page", "author": "Test Author"}

        document = Document(url=url, content=content, metadata=metadata)
        doc_dict = document.to_dict()

        assert isinstance(doc_dict, dict)
        assert doc_dict["url"] == url
        assert doc_dict["content"] == content
        assert doc_dict["metadata"] == metadata

    def test_with_empty_values(self):
        """Test Document with empty values."""
        document = Document(url="", content="", metadata={})

        assert document.url == ""
        assert document.content == ""
        assert document.metadata == {}
