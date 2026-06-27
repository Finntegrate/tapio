"""Tests for the Parser class."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

import pytest
import yaml

from tapio.config.config_manager import ConfigManager
from tapio.parser import Parser


class TestParser(unittest.TestCase):
    """Test the Parser functionality."""

    def setUp(self):
        """Set up test environment."""
        # Create temporary directories for testing
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.temp_dir, "config")

        # Create directories
        os.makedirs(self.config_dir, exist_ok=True)

        # Set up test site name
        self.site_name = "example"
        self.no_fallback_site_name = "no_fallback"
        self.domain = "example.com"

        # Patch DEFAULT_CONTENT_DIR and DEFAULT_DIRS to use temp_dir for isolation
        from tapio.config import settings as tapio_settings

        self._orig_content_dir = tapio_settings.DEFAULT_CONTENT_DIR
        tapio_settings.DEFAULT_CONTENT_DIR = self.temp_dir

        # Prepare input/output dir paths as used by Parser
        from tapio.config.settings import DEFAULT_DIRS

        self.DEFAULT_DIRS = DEFAULT_DIRS
        self.input_dir = os.path.join(self.temp_dir, self.site_name, DEFAULT_DIRS["CRAWLED_DIR"])
        self.output_dir = os.path.join(self.temp_dir, self.site_name, DEFAULT_DIRS["PARSED_DIR"])
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        # Create test HTML files directly in the crawled directory
        # Following site-based structure where files are organized by website paths
        with open(os.path.join(self.input_dir, "index.html"), "w") as f:
            f.write("""
            <html>
                <head><title>Example Website</title></head>
                <body>
                    <div id="main-content">
                        <h1>Example Website</h1>
                        <p>Welcome to the example website.</p>
                        <ul>
                            <li><a href="/page1">Page 1</a></li>
                            <li><a href="/page2">Page 2</a></li>
                        </ul>
                    </div>
                </body>
            </html>
            """)

        with open(os.path.join(self.input_dir, "about.html"), "w") as f:
            f.write("""
            <html>
                <head><title>About Example</title></head>
                <body>
                    <div class="content">
                        <h1>About Example</h1>
                        <p>This is the about page for the example website.</p>
                    </div>
                </body>
            </html>
            """)

        # Create HTML file without main-content div to test fallback selectors
        with open(os.path.join(self.input_dir, "no-main-content.html"), "w") as f:
            f.write("""
            <html>
                <head><title>No Main Content</title></head>
                <body>
                    <main>
                        <h1>Page Without Main Content Div</h1>
                        <p>This page doesn't have a main-content div.</p>
                    </main>
                </body>
            </html>
            """)

        # Create test files in subdirectories to test path-based structure
        # This simulates website paths like /en/about.html creating en/about.md
        en_dir = os.path.join(self.input_dir, "en")
        os.makedirs(en_dir, exist_ok=True)

        with open(os.path.join(en_dir, "services.html"), "w") as f:
            f.write("""
            <html>
                <head><title>Services</title></head>
                <body>
                    <div id="main-content">
                        <h1>Our Services</h1>
                        <p>We provide various services.</p>
                    </div>
                </body>
            </html>
            """)

        # Create custom test configuration
        self.test_config = {
            "sites": {
                "example": {
                    "base_url": f"https://{self.domain}",
                    "description": "Example Website for Testing",
                    "parser_config": {
                        "title_selector": "//title",
                        "content_selectors": [
                            '//div[@id="main-content"]',
                            '//div[@class="content"]',
                            "//main",
                        ],
                        "fallback_to_body": True,
                        "markdown_config": {"ignore_links": False, "body_width": 0},
                    },
                },
                "no_fallback": {
                    "base_url": f"https://{self.domain}",
                    "parser_config": {
                        "title_selector": "//h1",
                        "content_selectors": ['//div[@id="does-not-exist"]'],
                        "fallback_to_body": False,
                    },
                },
            },
        }

        # Save test configuration
        self.config_path = os.path.join(self.config_dir, "test_config.yaml")
        with open(self.config_path, "w") as f:
            yaml.dump(self.test_config, f)

        # Create config manager and get site config
        config_manager = ConfigManager(self.config_path)
        site_config = config_manager.get_site_config(self.site_name)

        # Create parser with injected dependencies
        self.parser = Parser(
            site_name=self.site_name,
            site_config=site_config,
            input_dir=self.input_dir,
            output_dir=self.output_dir,
        )

        # Mock the logger
        self.parser.logger = MagicMock()

    def tearDown(self):
        """Clean up after tests."""
        # Restore patched DEFAULT_CONTENT_DIR
        from tapio.config import settings as tapio_settings

        tapio_settings.DEFAULT_CONTENT_DIR = self._orig_content_dir
        shutil.rmtree(self.temp_dir)

    def test_init(self):
        """Test parser initialization."""
        self.assertEqual(self.parser.site, self.site_name)
        # Accept both possible input_dir values for cross-platform compatibility
        self.assertTrue(
            self.parser.input_dir == self.input_dir
            or os.path.abspath(self.parser.input_dir) == os.path.abspath(self.input_dir),
            f"Expected input_dir {self.input_dir}, got {self.parser.input_dir}",
        )
        self.assertTrue(
            self.parser.output_dir == self.output_dir
            or os.path.abspath(self.parser.output_dir) == os.path.abspath(self.output_dir),
            f"Expected output_dir {self.output_dir}, got {self.parser.output_dir}",
        )

        # Test config loaded correctly
        self.assertEqual(self.parser.config.parser_config.title_selector, "//title")
        self.assertEqual(len(self.parser.config.parser_config.content_selectors), 3)
        self.assertTrue(self.parser.config.parser_config.fallback_to_body)
        self.assertEqual(self.parser.config.description, "Example Website for Testing")

    def test_init_with_invalid_site(self):
        """Test initialization with invalid site."""
        config_manager = ConfigManager(self.config_path)
        with pytest.raises(ValueError, match="nonexistent"):
            config_manager.get_site_config("nonexistent")

    def test_parse_html_with_main_content(self):
        """Test parsing HTML with main-content div."""
        with open(os.path.join(self.input_dir, "index.html")) as f:
            html_content = f.read()

        title, content = self.parser._parse_html(html_content)

        self.assertEqual(title, "Example Website")
        self.assertIn("# Example Website", content)
        self.assertIn("Welcome to the example website", content)
        self.assertIn("Page 1", content)
        self.assertIn("Page 2", content)

    def test_parse_html_with_secondary_selector(self):
        """Test parsing HTML with secondary content selector."""
        with open(os.path.join(self.input_dir, "about.html")) as f:
            html_content = f.read()

        title, content = self.parser._parse_html(html_content)

        self.assertEqual(title, "About Example")
        self.assertIn("# About Example", content)
        self.assertIn("This is the about page", content)

    def test_parse_html_with_fallback(self):
        """Test fallback selector when primary selectors don't match."""
        with open(os.path.join(self.input_dir, "no-main-content.html")) as f:
            html_content = f.read()

        title, content = self.parser._parse_html(html_content)

        self.assertEqual(title, "No Main Content")
        self.assertIn("Page Without Main Content Div", content)
        self.assertIn("This page doesn't have a main-content div", content)

    def test_parse_html_without_fallback(self):
        """Test behavior when no selectors match and fallback is disabled."""
        # Create parser with no fallback config
        config_manager = ConfigManager(self.config_path)
        no_fallback_config = config_manager.get_site_config(self.no_fallback_site_name)

        # Prepare input/output directories for no_fallback site
        no_fallback_input_dir = os.path.join(
            self.temp_dir,
            self.no_fallback_site_name,
            self.DEFAULT_DIRS["CRAWLED_DIR"],
        )
        no_fallback_output_dir = os.path.join(
            self.temp_dir,
            self.no_fallback_site_name,
            self.DEFAULT_DIRS["PARSED_DIR"],
        )
        os.makedirs(no_fallback_input_dir, exist_ok=True)
        os.makedirs(no_fallback_output_dir, exist_ok=True)

        no_fallback_parser = Parser(
            site_name=self.no_fallback_site_name,
            site_config=no_fallback_config,
            input_dir=no_fallback_input_dir,
            output_dir=no_fallback_output_dir,
        )
        no_fallback_parser.logger = MagicMock()

        with open(os.path.join(self.input_dir, "index.html")) as f:
            html_content = f.read()

        title, content = no_fallback_parser._parse_html(html_content)

        # It should use the h1 selector for the title and return empty content
        self.assertEqual(title, "Example Website")
        self.assertEqual(content.strip(), "")
        no_fallback_parser.logger.warning.assert_called_with(
            "No content found and no fallback configured",
        )

    def test_html_to_markdown(self):
        """Test HTML to Markdown conversion with configs."""
        html = """
        <div>
            <h1>Test Header</h1>
            <p>This is a <strong>test</strong> paragraph with a <a href="https://example.com">link</a>.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </div>
        """

        markdown = self.parser._html_to_markdown(html)

        # Check for Markdown elements
        self.assertIn("# Test Header", markdown)
        self.assertIn("**test**", markdown)
        self.assertIn("[link]", markdown)
        self.assertIn("* Item 1", markdown)
        self.assertIn("* Item 2", markdown)

    def test_parse_all(self):
        """Test parsing all HTML files."""
        # Parse all files
        results = self.parser.parse_all()

        # Check that we parsed 4 files (3 in root + 1 in en/ subdirectory)
        self.assertEqual(
            len(results),
            4,
            f"Expected 4 parsed files, got {len(results)}. input_dir: {self.parser.input_dir}",
        )

        # Verify output directory structure.
        # With site-based structure, files placed directly in crawled directory
        # should create corresponding MD files directly in the output directory
        output_dir_contents = os.listdir(self.output_dir) if os.path.exists(self.output_dir) else "does not exist"

        # Verify the main index.html (parsed to index.md) file was created directly in output directory
        parsed_index_file = os.path.join(self.output_dir, "index.md")
        self.assertTrue(
            os.path.exists(parsed_index_file),
            f"Expected parsed index file {parsed_index_file} to exist. "
            f"Contents of {self.output_dir}: {output_dir_contents}.",
        )

        # Verify the en/services.html file created en/services.md with path structure preserved
        en_output_dir = os.path.join(self.output_dir, "en")
        self.assertTrue(
            os.path.exists(en_output_dir),
            f"Expected en subdirectory {en_output_dir} to exist.",
        )

        parsed_services_file = os.path.join(en_output_dir, "services.md")
        self.assertTrue(
            os.path.exists(parsed_services_file),
            f"Expected parsed services file {parsed_services_file} to exist.",
        )

        # Validate the content of parsed files
        titles = [result["title"] for result in results]
        self.assertIn("Example Website", titles)
        self.assertIn("About Example", titles)
        self.assertIn("No Main Content", titles)
        self.assertIn("Services", titles)

    def test_convert_element_link_to_absolute(self):
        """Test converting a single element's link attribute to absolute URL."""
        from lxml import html as lxml_html

        # Setup test cases
        base_url = "https://example.com/path/"
        absolute_prefixes = ("http://", "https://", "//", "mailto:", "#")

        # Case 1: Relative link that should be converted
        element1 = lxml_html.fromstring('<a href="page.html">Link</a>')
        result1 = Parser._convert_element_link_to_absolute(
            element1,
            "href",
            base_url,
            absolute_prefixes,
        )
        self.assertTrue(result1)
        self.assertEqual(element1.get("href"), "https://example.com/path/page.html")

        # Case 2: Relative link with leading slash
        element2 = lxml_html.fromstring('<a href="/another-page.html">Link</a>')
        result2 = Parser._convert_element_link_to_absolute(
            element2,
            "href",
            base_url,
            absolute_prefixes,
        )
        self.assertTrue(result2)
        self.assertEqual(element2.get("href"), "https://example.com/another-page.html")

        # Case 3: Absolute link that should not be converted (http://)
        element3 = lxml_html.fromstring('<a href="http://other-domain.com/page">Link</a>')
        result3 = Parser._convert_element_link_to_absolute(
            element3,
            "href",
            base_url,
            absolute_prefixes,
        )
        self.assertFalse(result3)
        self.assertEqual(element3.get("href"), "http://other-domain.com/page")

        # Case 4: Protocol-relative URL that should not be converted (//)
        element4 = lxml_html.fromstring('<a href="//cdn.example.com/script.js">Link</a>')
        result4 = Parser._convert_element_link_to_absolute(
            element4,
            "href",
            base_url,
            absolute_prefixes,
        )
        self.assertFalse(result4)
        self.assertEqual(element4.get("href"), "//cdn.example.com/script.js")

        # Case 5: Empty link
        element5 = lxml_html.fromstring('<a href="">Link</a>')
        result5 = Parser._convert_element_link_to_absolute(
            element5,
            "href",
            base_url,
            absolute_prefixes,
        )
        self.assertFalse(result5)  # Empty links are not considered for conversion
        self.assertEqual(element5.get("href"), "")

        # Case 6: Missing attribute
        element6 = lxml_html.fromstring("<a>Link</a>")
        result6 = Parser._convert_element_link_to_absolute(
            element6,
            "href",
            base_url,
            absolute_prefixes,
        )
        self.assertFalse(result6)
        self.assertIsNone(element6.get("href"))

    def test_convert_relative_links_to_absolute(self):
        """Test converting all relative links in HTML content to absolute URLs."""
        # Create HTML with various link types
        html_content = """
        <html>
            <body>
                <a href="relative.html">Relative Link</a>
                <a href="/root-relative.html">Root Relative Link</a>
                <a href="http://example.org/absolute">Absolute Link</a>
                <a href="https://example.org/secure">Secure Link</a>
                <a href="//cdn.example.org/script.js">Protocol Relative Link</a>
                <a href="mailto:test@example.com">Email Link</a>
                <a href="#section">Anchor Link</a>
                <img src="image.jpg">
                <img src="/images/logo.png">
                <img src="http://example.org/image.jpg">
                <img src="https://example.org/secure.jpg">
                <img src="//cdn.example.org/image.jpg">
                <img src="data:image/png;base64,abc123">
            </body>
        </html>
        """

        # Set the base URL
        self.parser.current_base_url = "https://test.com/subdir/"

        # Convert links
        result = self.parser._convert_relative_links_to_absolute(html_content)

        # Check that the conversion was successful
        self.assertIn('href="https://test.com/subdir/relative.html"', result)
        self.assertIn('href="https://test.com/root-relative.html"', result)
        self.assertIn('href="http://example.org/absolute"', result)  # Unchanged
        self.assertIn('href="https://example.org/secure"', result)  # Unchanged
        self.assertIn('href="//cdn.example.org/script.js"', result)  # Unchanged
        self.assertIn('href="mailto:test@example.com"', result)  # Unchanged
        self.assertIn('href="#section"', result)  # Unchanged
        self.assertIn('src="https://test.com/subdir/image.jpg"', result)
        self.assertIn('src="https://test.com/images/logo.png"', result)
        self.assertIn('src="http://example.org/image.jpg"', result)  # Unchanged
        self.assertIn('src="https://example.org/secure.jpg"', result)  # Unchanged
        self.assertIn('src="//cdn.example.org/image.jpg"', result)  # Unchanged
        self.assertIn('src="data:image/png;base64,abc123"', result)  # Unchanged

    def test_convert_relative_links_no_base_url(self):
        """Test that conversion is skipped when no base URL is available."""
        html_content = '<a href="page.html">Link</a>'
        self.parser.current_base_url = None
        result = self.parser._convert_relative_links_to_absolute(html_content)
        self.assertEqual(result, html_content)  # Should be unchanged
