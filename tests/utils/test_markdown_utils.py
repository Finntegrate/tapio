"""Tests for the markdown utilities."""

import os
import tempfile
from unittest.mock import mock_open, patch

from tapio.config.settings import DEFAULT_DIRS
from tapio.utils.markdown_utils import find_markdown_files, read_markdown_file


class TestMarkdownUtils:
    """Tests for the markdown utilities."""

    def test_read_markdown_file_with_source_url(self):
        """Test reading a markdown file with source_url in metadata."""
        mock_file_content = """---
title: Test Document
source_url: https://example.com/page.html
---
# Test Content

This is test content.
"""
        with patch("pathlib.Path.open", mock_open(read_data=mock_file_content)):
            metadata, content = read_markdown_file("test_file.md")

        assert metadata["title"] == "Test Document"
        assert metadata["source_url"] == "https://example.com/page.html"
        assert metadata["url"] == "https://example.com/page.html"
        assert content == "# Test Content\n\nThis is test content."  # No trailing newline

    def test_read_markdown_file_with_source_file(self):
        """Test reading a markdown file with source_file in metadata."""
        mock_file_content = f"""---
title: Test Document
source_file: {DEFAULT_DIRS["CRAWLED_DIR"]}/example.com/page.html
---
# Test Content

This is test content.
"""
        with patch("pathlib.Path.open", mock_open(read_data=mock_file_content)):
            metadata, content = read_markdown_file("test_file.md")

        assert metadata["title"] == "Test Document"
        assert metadata["source_file"] == f"{DEFAULT_DIRS['CRAWLED_DIR']}/example.com/page.html"
        assert metadata["url"] == "example.com/page.html"
        assert content == "# Test Content\n\nThis is test content."  # No trailing newline

    def test_read_markdown_file_error(self):
        """Test error handling when reading a markdown file."""
        with patch("pathlib.Path.open", side_effect=FileNotFoundError("File not found")):
            metadata, content = read_markdown_file("non_existent.md")

        assert metadata == {}
        assert content == ""

    def test_find_markdown_files_no_filter(self):
        """Test finding markdown files without site filter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some test files
            os.makedirs(os.path.join(temp_dir, "subdir"), exist_ok=True)
            open(os.path.join(temp_dir, "file1.md"), "w").close()
            open(os.path.join(temp_dir, "file2.txt"), "w").close()
            open(os.path.join(temp_dir, "subdir", "file3.md"), "w").close()

            # Find markdown files
            markdown_files = find_markdown_files(temp_dir)

            # Check that the correct files were found
            assert len(markdown_files) == 2
            assert any(f.endswith("file1.md") for f in markdown_files)
            assert any(f.endswith(os.path.join("subdir", "file3.md")) for f in markdown_files)
            assert not any(f.endswith("file2.txt") for f in markdown_files)

    def test_find_markdown_files_with_site_filter(self):
        """Test finding markdown files with site filter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create site directory structure
            migri_dir = os.path.join(temp_dir, "migri", "parsed")
            kela_dir = os.path.join(temp_dir, "kela", "parsed")
            os.makedirs(migri_dir, exist_ok=True)
            os.makedirs(kela_dir, exist_ok=True)

            # Create test files in different site directories
            file1_path = os.path.join(migri_dir, "file1.md")
            with open(file1_path, "w") as f:
                f.write("""---
title: Migri Document
---
# Test Content
""")

            file2_path = os.path.join(kela_dir, "file2.md")
            with open(file2_path, "w") as f:
                f.write("""---
title: Kela Document
---
# Other Content
""")

            # Find markdown files with site filter
            markdown_files = find_markdown_files(temp_dir, site_filter="migri")

            # Check that only the file in the migri site directory was found
            assert len(markdown_files) == 1
            assert any(f.endswith("file1.md") for f in markdown_files)
            assert not any(f.endswith("file2.md") for f in markdown_files)

    def test_find_markdown_files_with_unparseable_file(self):
        """Test finding markdown files with one that can't be parsed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create site directory structure
            migri_dir = os.path.join(temp_dir, "migri", "parsed")
            os.makedirs(migri_dir, exist_ok=True)

            # Create a valid file
            file1_path = os.path.join(migri_dir, "file1.md")
            with open(file1_path, "w") as f:
                f.write("""---
title: Test Document
---
# Test Content
""")

            # Create an invalid file (invalid YAML frontmatter) - but it should still be found since we
            # filter by directory structure
            file2_path = os.path.join(migri_dir, "file2.md")
            with open(file2_path, "w") as f:
                f.write("""---
title: - [Invalid YAML
---
# Invalid Content
""")

            # Find markdown files with site filter
            markdown_files = find_markdown_files(temp_dir, site_filter="migri")

            # Check that both files were found (since we filter by directory structure, not content)
            assert len(markdown_files) == 2
            assert any(f.endswith("file1.md") for f in markdown_files)
            assert any(f.endswith("file2.md") for f in markdown_files)

    def test_find_markdown_files_error(self):
        """Test error handling when finding markdown files."""
        with patch("pathlib.Path.rglob", side_effect=PermissionError("Permission denied")):
            markdown_files = find_markdown_files("non_existent_dir")

        assert markdown_files == []
