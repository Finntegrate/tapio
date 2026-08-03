"""Tests for the text utilities."""

from unittest.mock import Mock, patch

from tapio.utils.text_utils import (
    _basic_clean_html,
    _chunk_text_safely,
    chunk_html_content,
    is_pdf_url,
    remove_javascript,
)


class TestTextUtils:
    """Tests for the text utilities."""

    def test_is_pdf_url_with_pdf_extension(self):
        """Test is_pdf_url with URLs that end with .pdf."""
        assert is_pdf_url("https://example.com/document.pdf") is True
        assert is_pdf_url("https://example.com/document.PDF") is True
        assert is_pdf_url("/documents/report.pdf") is True

    def test_is_pdf_url_with_pdf_in_path(self):
        """Test is_pdf_url with URLs that have 'pdf' in the path."""
        assert is_pdf_url("https://example.com/pdf-document") is True
        assert is_pdf_url("https://example.com/documents/PDF_report") is True

    def test_is_pdf_url_non_pdf(self):
        """Test is_pdf_url with URLs that do not point to PDFs."""
        assert is_pdf_url("https://example.com/document.html") is False
        assert is_pdf_url("https://example.com/page") is False
        assert is_pdf_url("/documents/report.docx") is False
        # PDF in domain should not be detected as PDF file
        assert is_pdf_url("https://pdf.example.com/page.html") is False

    def test_remove_javascript(self):
        """Test removing JavaScript from HTML content."""
        html_with_js = """
        <html>
        <head>
            <script>alert('test');</script>
        </head>
        <body>
            <div onclick="alert('clicked')">Click me</div>
            <a href="javascript:void(0)">Link</a>
            <script src="external.js"></script>
        </body>
        </html>
        """

        cleaned_html = remove_javascript(html_with_js)

        # Check that script tags are removed
        assert "<script>" not in cleaned_html
        assert "<script src=" not in cleaned_html
        assert "alert('test');" not in cleaned_html

        # Check that event handlers are removed
        assert "onclick=" not in cleaned_html

        # Check that javascript: URLs are replaced
        assert "javascript:void(0)" not in cleaned_html
        assert 'href="#"' in cleaned_html

        # Check that content is preserved (accounting for spacing differences)
        assert "Click me" in cleaned_html
        assert "<a href=" in cleaned_html

    def test_chunk_html_content_small_content(self):
        """Test chunking small HTML content that doesn't need chunking."""
        html = "<p>Small content</p>"
        chunks = chunk_html_content(html, "text/html", chunk_size=1000)

        assert len(chunks) == 1
        assert "Small content" in chunks[0]["content"]

    def test_chunk_html_content_non_html(self):
        """Test chunking non-HTML content."""
        plain_text = "This is plain text content" * 50  # Make it large enough to chunk
        chunks = chunk_html_content(
            plain_text,
            "text/plain",
            chunk_size=500,
            chunk_overlap=50,
        )

        assert len(chunks) > 1
        assert all(isinstance(chunk, dict) for chunk in chunks)
        assert all("content" in chunk for chunk in chunks)
        assert all("metadata" in chunk for chunk in chunks)
        assert all(len(chunk["content"]) <= 500 for chunk in chunks)

    @patch("tapio.utils.text_utils.HTMLHeaderTextSplitter")
    @patch("tapio.utils.text_utils.re.sub")
    def test_chunk_html_content_header_splitter(self, mock_re_sub, mock_splitter_class):
        """Test chunking HTML content with header splitter."""
        # Make the plain text extraction return something large enough to trigger chunking
        mock_re_sub.return_value = "A" * 2000

        mock_splitter = Mock()
        mock_splitter_class.return_value = mock_splitter
        mock_docs = [
            Mock(page_content="Content 1", metadata={"header": "Header 1"}),
            Mock(page_content="Content 2", metadata={"header": "Header 2"}),
        ]
        mock_splitter.split_text.return_value = mock_docs

        html = "<h1>Header 1</h1><p>Content 1</p><h2>Header 2</h2><p>Content 2</p>"
        chunks = chunk_html_content(html, "text/html", splitter_type="header")

        mock_splitter.split_text.assert_called_once()
        assert len(chunks) == 2
        assert chunks[0]["content"] == "Content 1"
        assert chunks[1]["content"] == "Content 2"

    @patch("tapio.utils.text_utils.HTMLSectionSplitter")
    @patch("tapio.utils.text_utils.re.sub")
    def test_chunk_html_content_section_splitter(
        self,
        mock_re_sub,
        mock_splitter_class,
    ):
        """Test chunking HTML content with section splitter."""
        # Make the plain text extraction return something large enough to trigger chunking
        mock_re_sub.return_value = "A" * 2000

        mock_splitter = Mock()
        mock_splitter_class.return_value = mock_splitter
        mock_docs = [
            Mock(page_content="Section 1", metadata={"section": "Section 1"}),
            Mock(page_content="Section 2", metadata={"section": "Section 2"}),
        ]
        mock_splitter.split_text.return_value = mock_docs

        html = "<div>Section 1</div><div>Section 2</div>"
        chunks = chunk_html_content(html, "text/html", splitter_type="section")

        mock_splitter.split_text.assert_called_once()
        assert len(chunks) == 2
        assert chunks[0]["content"] == "Section 1"
        assert chunks[1]["content"] == "Section 2"

    @patch("tapio.utils.text_utils.RecursiveCharacterTextSplitter")
    @patch("tapio.utils.text_utils.re.sub")
    @patch("tapio.utils.text_utils._basic_clean_html")
    def test_chunk_html_content_semantic_splitter(
        self,
        mock_clean_html,
        mock_re_sub,
        mock_splitter_class,
    ):
        """Test chunking HTML content with semantic (recursive) splitter."""
        # Make the plain text extraction return something large enough to trigger chunking
        mock_re_sub.return_value = "A" * 2000
        mock_clean_html.return_value = "<p>Cleaned HTML</p>"

        mock_splitter = Mock()
        mock_splitter_class.return_value = mock_splitter
        mock_docs = [
            Mock(page_content="Chunk 1", metadata={}),
            Mock(page_content="Chunk 2", metadata={}),
        ]
        mock_splitter.create_documents.return_value = mock_docs

        html = "<p>Chunk 1</p><p>Chunk 2</p>"
        chunks = chunk_html_content(html, "text/html", splitter_type="semantic")

        mock_splitter_class.assert_called_once()
        mock_splitter.create_documents.assert_called_once()
        assert len(chunks) == 2
        assert chunks[0]["content"] == "Chunk 1"
        assert chunks[1]["content"] == "Chunk 2"

    def test_chunk_html_content_error_handling(self):
        """Test error handling in chunk_html_content."""
        with patch(
            "tapio.utils.text_utils.RecursiveCharacterTextSplitter",
        ) as mock_splitter_class:
            mock_splitter = Mock()
            mock_splitter_class.return_value = mock_splitter
            mock_splitter.create_documents.side_effect = ValueError("Test error")

            html = "<p>Content with error</p>" * 100
            chunks = chunk_html_content(html, "text/html")

            # Should fall back to _chunk_text_safely
            assert len(chunks) > 0
            assert all(isinstance(chunk, dict) for chunk in chunks)

    def test_chunk_text_safely(self):
        """Test chunking text safely with limits."""
        text = "This is a test." * 100  # Create text long enough to split
        chunks = _chunk_text_safely(
            text,
            chunk_size=100,
            chunk_overlap=20,
            max_chunks=5,
        )

        assert len(chunks) <= 5
        assert all(len(chunk["content"]) <= 100 for chunk in chunks)

    def test_chunk_text_safely_error(self):
        """Test error handling in _chunk_text_safely."""
        with patch(
            "tapio.utils.text_utils.RecursiveCharacterTextSplitter",
        ) as mock_splitter_class:
            mock_splitter = Mock()
            mock_splitter_class.return_value = mock_splitter
            mock_splitter.create_documents.side_effect = ValueError("Test error")

            # Mock the manual chunking as well to ensure we get results
            with patch(
                "tapio.utils.text_utils.logger.exception",
            ) as mock_logging:
                # Create long enough text to trigger chunking
                text = "Test content " * 100
                _ = _chunk_text_safely(
                    text,
                    chunk_size=100,
                    chunk_overlap=20,
                    max_chunks=3,
                )

                # Verify the error was logged
                mock_logging.assert_called_once()
                assert "Error chunking text" in mock_logging.call_args[0][0]

    def test_basic_clean_html(self):
        """Test basic HTML cleaning."""
        html = """
        <html>
        <head>
            <style>body {color: red;}</style>
            <script>console.log('test');</script>
        </head>
        <body>
            <!-- This is a comment -->
            <h1 class="title">Title</h1>
            <p>This is a <b>paragraph</b> with formatting.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </body>
        </html>
        """

        cleaned = _basic_clean_html(html)

        # Check that styles, scripts, and comments are removed
        assert "style" not in cleaned
        assert "script" not in cleaned
        assert "comment" not in cleaned

        # Check that headers are converted to markdown-like format
        assert "# Title" in cleaned

        # Check that paragraphs are preserved with newlines
        assert "This is a paragraph with formatting" in cleaned

        # Check that list items are converted to bullet points
        assert "• Item 1" in cleaned
        assert "• Item 2" in cleaned
