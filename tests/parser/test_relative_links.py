"""Tests for handling relative links in Parser."""

import json
import os
import shutil
import tempfile
import unittest

import yaml

from tapio.config.config_manager import ConfigManager
from tapio.parser import Parser


class TestRelativeLinks(unittest.TestCase):
    """Test the relative link conversion functionality."""

    def setUp(self):
        """Set up test environment."""
        # Create temporary directories for testing
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.temp_dir, "config")

        # Patch DEFAULT_CONTENT_DIR and DEFAULT_DIRS to use temp_dir for isolation
        from tapio.config import settings as tapio_settings

        self._orig_content_dir = tapio_settings.DEFAULT_CONTENT_DIR
        tapio_settings.DEFAULT_CONTENT_DIR = self.temp_dir
        from tapio.config.settings import DEFAULT_DIRS

        self.input_dir = os.path.join(self.temp_dir, "test_site", DEFAULT_DIRS["CRAWLED_DIR"])
        self.output_dir = os.path.join(self.temp_dir, "test_site", DEFAULT_DIRS["PARSED_DIR"])
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.config_dir, exist_ok=True)

        # Create test domain directories
        self.domain = "test-site.com"
        self.domain_dir = os.path.join(self.input_dir, self.domain)
        os.makedirs(self.domain_dir, exist_ok=True)

        # Create test HTML file with relative links
        self.test_html_path = os.path.join(self.domain_dir, "page-with-links.html")
        with open(self.test_html_path, "w") as f:
            f.write("""
            <html>
                <head><title>Page with Links</title></head>
                <body>
                    <div id="content">
                        <h1>Page with Links</h1>
                        <p>This page has <a href="/relative/path">relative links</a>.</p>
                        <img src="/images/test.png" alt="Test Image">
                        <p>Here's an <a href="https://example.com">absolute link</a>.</p>
                        <p>And an <a href="page2.html">relative link without slash</a>.</p>
                    </div>
                </body>
            </html>
            """)

        # Create URL mappings file
        self.url_mappings = {
            f"{self.domain}/page-with-links.html": {
                "url": f"https://{self.domain}/page-with-links",
                "timestamp": "2025-05-10T12:00:00Z",
            },
        }
        with open(os.path.join(self.input_dir, "url_mappings.json"), "w") as f:
            json.dump(self.url_mappings, f)

        # Create test configuration
        self.test_config = {
            "sites": {
                "test_site": {
                    "site_name": "test_site",
                    "base_url": f"https://{self.domain}",
                    "base_dir": self.domain,
                    "title_selector": "//title",
                    "content_selectors": ['//div[@id="content"]'],
                    "fallback_to_body": True,
                    "markdown_config": {"ignore_links": False, "body_width": 0},
                },
            },
        }

        # Save test configuration
        self.config_path = os.path.join(self.config_dir, "test_config.yaml")
        with open(self.config_path, "w") as f:
            yaml.dump(self.test_config, f)

        # Create config manager and get site config
        config_manager = ConfigManager(self.config_path)
        site_config = config_manager.get_site_config("test_site")

        # Create parser with injected dependencies
        self.parser = Parser(
            site_name="test_site",
            site_config=site_config,
            input_dir=self.input_dir,
            output_dir=self.output_dir,
        )

    def tearDown(self):
        """Clean up after tests."""
        from tapio.config import settings as tapio_settings

        tapio_settings.DEFAULT_CONTENT_DIR = self._orig_content_dir
        shutil.rmtree(self.temp_dir)

    def test_convert_relative_links(self):
        """Test conversion of relative links to absolute URLs."""
        test_html = """
        <div>
            <a href="/relative/path">Relative Link</a>
            <a href="relative/path2">Relative Link 2</a>
            <img src="/images/test.jpg" alt="Test">
            <a href="https://absolute.com/path">Absolute Link</a>
        </div>
        """

        # Set the base URL
        self.parser.current_base_url = f"https://{self.domain}"

        # Convert links
        result = self.parser._convert_relative_links_to_absolute(test_html)

        # Check that relative links were converted
        self.assertIn(f'href="https://{self.domain}/relative/path"', result)
        self.assertIn(f'href="https://{self.domain}/relative/path2"', result)
        self.assertIn(f'src="https://{self.domain}/images/test.jpg"', result)

        # Check that absolute links were not modified
        self.assertIn('href="https://absolute.com/path"', result)

    def test_parse_html_with_relative_links(self):
        """Test end-to-end parsing of HTML with relative links."""
        # First set the base URL manually
        self.parser.current_base_url = f"https://{self.domain}"

        with open(self.test_html_path) as f:
            html_content = f.read()

        # Parse the HTML
        _, markdown_content = self.parser._parse_html(html_content)

        # Check that relative links were converted in the markdown
        self.assertIn(f"https://{self.domain}/relative/path", markdown_content)
        self.assertIn(f"https://{self.domain}/images/test.png", markdown_content)
        self.assertIn("https://example.com", markdown_content)
        self.assertIn(f"https://{self.domain}/page2.html", markdown_content)

    def test_parse_file(self):
        """Test that parse_file sets the correct base URL."""
        # Parse the file
        result = self.parser.parse_file(self.test_html_path)

        # Verify the result
        self.assertIsNotNone(result, f"parse_file returned None for {self.test_html_path}")
        # Accept both possible base URLs: with and without trailing path
        expected_base_urls = [f"https://{self.domain}/page-with-links", f"https://{self.domain}/"]
        self.assertIn(
            self.parser.current_base_url,
            expected_base_urls,
            f"Expected base_url in {expected_base_urls}, got {self.parser.current_base_url}",
        )

        # Read the output markdown file to verify links were converted
        output_path = result["output_file"]
        with open(output_path) as f:
            markdown_content = f.read()

        # Check links in the markdown
        self.assertIn(f"https://{self.domain}/relative/path", markdown_content)
        self.assertIn(f"https://{self.domain}/images/test.png", markdown_content)
        self.assertIn(f"https://{self.domain}/page2.html", markdown_content)

    def test_domain_specific_url_handling(self):
        """Test handling of domain-specific URLs."""
        # Create a file in a domain-specific directory
        domain_file_path = os.path.join(self.domain_dir, "subdir", "domain-specific.html")
        os.makedirs(os.path.dirname(domain_file_path), exist_ok=True)

        with open(domain_file_path, "w") as f:
            f.write("""
            <html>
                <head><title>Domain Specific</title></head>
                <body>
                    <div id="content">
                        <h1>Domain Specific Page</h1>
                        <p>This page has <a href="/domain/path">relative domain links</a>.</p>
                        <img src="/domain/image.png" alt="Domain Image">
                    </div>
                </body>
            </html>
            """)

        # Update test configuration with domain-specific base URL and dir
        self.test_config["sites"]["test_site"]["base_url"] = f"https://{self.domain}"
        self.test_config["sites"]["test_site"]["base_dir"] = self.domain

        # Save updated test configuration
        with open(self.config_path, "w") as f:
            yaml.dump(self.test_config, f)

        # Create a new parser with the updated config using dependency injection
        config_manager = ConfigManager(self.config_path)
        site_config = config_manager.get_site_config("test_site")

        parser = Parser(
            site_name="test_site",
            site_config=site_config,
            input_dir=self.input_dir,
            output_dir=self.output_dir,
        )

        # Delete URL mappings to force using domain-based URL construction
        parser.url_mappings = {}

        # Parse the file
        result = parser.parse_file(domain_file_path)

        self.assertIsNotNone(result, f"parse_file returned None for {domain_file_path}")
        self.assertIsNotNone(parser.current_base_url, "current_base_url is None after parsing")
        self.assertTrue(parser.current_base_url and parser.current_base_url.startswith(f"https://{self.domain}"))

        # Read the output markdown file to verify links were converted
        output_path = result["output_file"]
        with open(output_path) as f:
            markdown_content = f.read()

        # Check that relative links were converted to absolute using the domain
        self.assertIn(f"https://{self.domain}/domain/path", markdown_content)
        self.assertIn(f"https://{self.domain}/domain/image.png", markdown_content)
