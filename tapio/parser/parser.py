"""HTML content parser module.

This module contains the Parser class, which loads site-specific
configurations and extracts content from HTML pages accordingly.
"""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import html2text
import yaml
from lxml import html

from tapio.config import (
    ConfigManager,
)
from tapio.config.config_models import SiteConfig

# Minimum path parts (subdir + filename) to preserve directory structure in output
MIN_NESTED_PATH_PARTS = 2


class DirectoryScope:
    """Context manager for temporarily changing directory context without modifying instance state.

    This provides a thread-safe way to create a scoped directory context without
    directly modifying the instance's state.
    """

    def __init__(self, original_path: str, scoped_path: str) -> None:
        """Initialize the directory scope context manager.

        Args:
            original_path: The original directory path to preserve
            scoped_path: The temporarily scoped directory path to use
        """
        self.original_path = original_path
        self.scoped_path = scoped_path

    def __enter__(self) -> str:
        """Enter the context with the scoped directory."""
        return self.scoped_path

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit the context, no cleanup needed as we don't modify state.

        Args:
            exc_type: The exception type if an exception was raised in the context
            exc_val: The exception value if an exception was raised in the context
            exc_tb: The traceback if an exception was raised in the context
        """


class Parser:
    """HTML content parser that uses site-specific configurations.

    This parser loads configurations for different websites and extracts
    content using the appropriate selectors for each site. Configuration
    and directory paths are injected to enable testing and reuse.
    """

    def __init__(
        self,
        site_name: str,
        site_config: SiteConfig,
        input_dir: str,
        output_dir: str,
    ) -> None:
        """Initialize the parser.

        Args:
            site_name: Name of the site being parsed
            site_config: Site-specific configuration with selectors
            input_dir: Directory containing crawled HTML files
            output_dir: Directory for output markdown files

        Example:
            >>> from tapio.config.config_manager import ConfigManager
            >>> from tapio.config import settings
            >>>
            >>> config_manager = ConfigManager()
            >>> site_config = config_manager.get_site_config("migri")
            >>> input_dir = os.path.join(settings.DEFAULT_CONTENT_DIR, "migri", "crawled")
            >>> output_dir = os.path.join(settings.DEFAULT_CONTENT_DIR, "migri", "parsed")
            >>> parser = Parser("migri", site_config, input_dir, output_dir)
        """
        self.site = site_name
        self.config = site_config
        self.input_dir = input_dir
        self.output_dir = output_dir

        self.current_base_url: str | None = None  # Will store the base URL of the current document

        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        # Load URL mappings if available
        self.url_mappings: dict[str, dict[str, str]] = {}
        self._load_url_mappings()

        # Create output directory if it doesn't exist
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        self.logger.info("Initialized Parser for %s", self.site)

    def setup_logging(self) -> None:
        """Set up logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.StreamHandler()],
        )

    def _load_url_mappings(self) -> None:
        """Load URL mappings from the JSON file."""
        mapping_file = Path(self.input_dir) / "url_mappings.json"
        if mapping_file.exists():
            try:
                with mapping_file.open(encoding="utf-8") as f:
                    self.url_mappings = json.load(f)
                self.logger.info("Loaded %d URL mappings", len(self.url_mappings))
            except Exception:
                self.logger.exception("Error loading URL mappings")
        else:
            self.logger.warning("URL mapping file not found: %s", mapping_file)
            # Still continue processing - URL mappings are optional

    def _get_original_url(self, file_path: str | Path) -> str | None:
        """Get the original URL for a file path from the URL mappings.

        Args:
            file_path: Path to the HTML file

        Returns:
            Original URL or None if not found
        """
        file_path_str = str(file_path)

        # Try different lookup strategies
        url = (
            self._try_exact_match(file_path_str)
            or self._try_relative_path_match(file_path_str)
            or self._try_filename_match(file_path_str)
        )

        if not url:
            self.logger.debug("No URL mapping found for %s", file_path)
        return url

    def _try_exact_match(self, file_path_str: str) -> str | None:
        """Try exact match in URL mappings.

        Args:
            file_path_str: String representation of the file path

        Returns:
            Original URL or None if not found
        """
        for key, value in self.url_mappings.items():
            if file_path_str.endswith(key):
                return value.get("url")
        return None

    def _try_relative_path_match(self, file_path_str: str) -> str | None:
        """Try relative path matching with OS compatibility.

        Args:
            file_path_str: String representation of the file path

        Returns:
            Original URL or None if not found
        """
        try:
            rel_path = os.path.relpath(file_path_str, self.input_dir)
            # Check both slash directions
            for path_variant in [rel_path, rel_path.replace("\\", "/")]:
                if path_variant in self.url_mappings:
                    return self.url_mappings[path_variant].get("url")
        except Exception as e:
            self.logger.debug("Error in relative path matching: %s", e)
        return None

    def _try_filename_match(self, file_path_str: str) -> str | None:
        """Try matching by filename only.

        Args:
            file_path_str: String representation of the file path

        Returns:
            Original URL or None if not found
        """
        try:
            filename = Path(file_path_str).name
            for key, value in self.url_mappings.items():
                if key.endswith(filename):
                    return value.get("url")
        except Exception as e:
            self.logger.debug("Error in filename matching: %s", e)
        return None

    # The _load_site_config and _load_config_registry methods have been replaced
    # by using the ConfigManager from tapio.config

    def _parse_html(self, html_content: str) -> tuple[str, str]:
        """Parse HTML content using site-specific selectors.

        Args:
            html_content: Raw HTML content

        Returns:
            Tuple containing (title, content)
        """
        try:
            # Parse the HTML content
            tree = html.fromstring(html_content)

            # Extract the title using the configured selector
            title_elements = tree.xpath(self.config.parser_config.title_selector)
            title = title_elements[0].text if title_elements else "Untitled"

            # Find content using the configured selectors
            content_section = self.config.parser_config.get_content_selector(tree)

            # Prepare HTML content for conversion
            if content_section is not None:
                # Get the HTML of just this element
                content_html = html.tostring(
                    content_section,
                    encoding="unicode",
                    pretty_print=True,
                )
                self.logger.info("Successfully extracted content section")
            elif self.config.parser_config.fallback_to_body:
                # If no content section found and fallback is enabled, use the body
                body = tree.xpath("//body")
                content_html = html.tostring(body[0], encoding="unicode", pretty_print=True) if body else html_content
                self.logger.warning(
                    "Could not find specific content section, using body content",
                )
            else:
                # Return empty content if no fallback and no match
                self.logger.warning("No content found and no fallback configured")
                content_html = ""

            # Convert relative links to absolute links
            content_html = self._convert_relative_links_to_absolute(content_html)

            # Convert HTML to Markdown using site-specific settings
            markdown_content = self._html_to_markdown(content_html)

        except Exception as e:
            self.logger.exception("Error parsing HTML")
            return "Error Parsing Page", f"Error parsing the HTML content: {e!s}"
        else:
            return title, markdown_content

    @staticmethod
    def _convert_element_link_to_absolute(
        element: html.HtmlElement,
        attribute: str,
        base_url: str,
        absolute_prefixes: tuple[str, ...],
    ) -> bool:
        """Convert a single element's link attribute to absolute URL if it's relative.

        Args:
            element: HTML element to process
            attribute: Attribute name (e.g., 'href', 'src')
            base_url: Base URL to use for conversion
            absolute_prefixes: Tuple of prefixes that indicate absolute URLs

        Returns:
            True if the link was converted, False otherwise
        """
        link = element.get(attribute)
        if not link or link.startswith(absolute_prefixes):
            return False

        absolute_url = urljoin(base_url, link)
        element.set(attribute, absolute_url)
        return True

    def _convert_relative_links_to_absolute(self, html_content: str) -> str:
        """Convert relative links in HTML content to absolute URLs.

        Args:
            html_content: HTML content with potentially relative links

        Returns:
            HTML content with relative links converted to absolute URLs
        """
        if not self.current_base_url:
            return html_content  # No base URL available, return unchanged

        try:
            # Parse the HTML
            tree = html.fromstring(html_content)

            # Define absolute prefixes for different attribute types
            href_prefixes = ("http://", "https://", "//", "mailto:", "#", "tel:")
            src_prefixes = ("http://", "https://", "//", "data:")

            # Find all links and process them
            for element in tree.xpath("//*[@href]"):
                self._convert_element_link_to_absolute(
                    element,
                    "href",
                    self.current_base_url,
                    href_prefixes,
                )

            # Find all images and process them
            for element in tree.xpath("//*[@src]"):
                self._convert_element_link_to_absolute(
                    element,
                    "src",
                    self.current_base_url,
                    src_prefixes,
                )

            # Convert back to string
            return html.tostring(tree, encoding="unicode", pretty_print=True)
        except Exception:
            self.logger.exception("Error converting relative links")
            return html_content  # Return original content if there's an error

    def _html_to_markdown(self, html_content: str) -> str:
        """Convert HTML to Markdown using site-specific configuration.

        Args:
            html_content: HTML content to convert

        Returns:
            Markdown formatted text
        """
        # Configure html2text with site-specific settings
        config = self.config.parser_config.markdown_config
        text_maker = html2text.HTML2Text()
        text_maker.ignore_links = config.ignore_links
        text_maker.body_width = config.body_width
        text_maker.protect_links = config.protect_links
        text_maker.unicode_snob = config.unicode_snob
        text_maker.ignore_images = config.ignore_images
        text_maker.ignore_tables = config.ignore_tables

        # Convert HTML to Markdown
        return text_maker.handle(html_content)

    def _construct_base_url_from_path(self, file_path: str) -> str:
        """Construct base URL from file path when no URL mapping exists.

        Args:
            file_path: Path to the HTML file

        Returns:
            Constructed base URL
        """
        try:
            # Calculate relative path directly from the input directory
            rel_path = os.path.relpath(file_path, self.input_dir)

            if rel_path.startswith(".."):
                # File is outside input directory
                self.logger.info("File outside input dir, using base URL: %s", self.config.base_url)
                return str(self.config.base_url)

            # Normalize path and construct URL
            normalized_path = rel_path.replace("\\", "/")
            # Convert HttpUrl to string for urljoin
            base_url_str = str(self.config.base_url)
            constructed_url = urljoin(base_url_str, normalized_path)
            self.logger.info("Constructed base URL: %s", constructed_url)

        except ValueError:
            self.logger.warning(
                "Error constructing URL from path, using base URL: %s",
                self.config.base_url,
            )
            return str(self.config.base_url)
        else:
            return constructed_url

    def _extract_domain_from_path(self, file_path: str | Path) -> str:
        """Extract the first part of the path (typically a domain or language directory).

        Args:
            file_path: Path to the HTML file

        Returns:
            First directory name from the relative path or "unknown" if not found
        """
        try:
            # Get the path relative to the input directory
            rel_path = Path(file_path).relative_to(Path(self.input_dir))
            path_parts = rel_path.parts
            first_part = path_parts[0] if len(path_parts) > 0 else "unknown"
        except ValueError:
            return "unknown"
        else:
            return first_part

    def _create_directory_scope(self) -> DirectoryScope:
        """Create a directory scope for operations on the input directory.

        Returns:
            A DirectoryScope context manager that can be used in a with statement
        """
        # Return the input directory as the scoped directory
        # Note: The original path structure from the input directory is preserved
        # in the output through the _get_output_filename method, which maintains
        # the same directory hierarchy (e.g., language directories, etc.)
        return DirectoryScope(self.input_dir, self.input_dir)

    def _parse_file_with_context(
        self,
        html_file: str | Path,
    ) -> dict[str, Any] | None:
        """Parse a single file with URL context preservation.

        Args:
            html_file: Path to the HTML file to parse

        Returns:
            Dictionary containing information about the parsed file or None if parsing failed
        """
        try:
            # Parse the file with URL context preservation
            return self.parse_file(html_file, preserve_url_context=True)

        except Exception:
            self.logger.exception("Error parsing %s with context", html_file)
            return None

    def parse_file(
        self,
        html_file: str | Path,
        preserve_url_context: bool = False,
    ) -> dict[str, Any] | None:
        """Parse a single HTML file from the configured domain.

        Args:
            html_file: Path to the HTML file
            preserve_url_context: If True, don't restore original base_url after parsing,
                                 needed for batch processing

        Returns:
            Dictionary containing information about the parsed file
        """
        # Get the original URL of this file from URL mappings if available
        original_url = self._get_original_url(html_file)

        # Store original base_url only if we need to restore it later
        original_base_url = self.current_base_url if not preserve_url_context else None

        # Set the current base URL for this parse operation
        self.current_base_url = original_url

        # If no URL mapping found, construct URL from configuration and file path
        if not self.current_base_url:
            file_path_str = str(html_file)
            self.current_base_url = self._construct_base_url_from_path(file_path_str)

        # Parse the file
        html_file_path = Path(html_file)
        self.logger.info("Parsing %s", html_file_path)

        try:
            # Read the HTML content
            with html_file_path.open(encoding="utf-8") as f:
                html_content = f.read()

            # Extract the domain from the file path
            domain = self._extract_domain_from_path(html_file_path)

            # Generate a filename for the output markdown
            output_filename = self._get_output_filename(html_file_path)

            # Parse the HTML content
            title, content = self._parse_html(html_content)

            # Create metadata for the markdown file
            metadata = self._create_metadata(html_file_path, title)

            # Save the content as Markdown with frontmatter
            output_path = self._save_markdown(output_filename, title, content, metadata)

            return {
                "source_file": str(html_file_path),
                "output_file": output_path,
                "title": title,
                "domain": domain,
            }

        except Exception:
            self.logger.exception("Error parsing %s", html_file_path)
            return None
        finally:
            # Restore the original base URL only if not preserving context
            if original_base_url is not None and not preserve_url_context:
                self.current_base_url = original_base_url

    def _create_metadata(self, file_path: str | Path, title: str) -> dict[str, Any]:
        """Create metadata for the markdown file including the original URL.

        Args:
            file_path: Path to the HTML file
            title: Title of the page

        Returns:
            Dictionary with metadata
        """
        # Extract domain using the helper method
        domain = self._extract_domain_from_path(file_path)

        # Basic metadata
        metadata = {
            "source_file": str(file_path),
            "title": title,
            "domain": domain,
            "parse_timestamp": datetime.now(UTC).isoformat(),
            "parser": self.__class__.__name__,
        }

        # Add the original URL to the metadata if available
        original_url = self._get_original_url(file_path)
        if original_url:
            metadata["source_url"] = original_url

        return metadata

    def _get_output_filename(self, html_file_path: Path) -> str:
        """Generate an output filename for the parsed markdown file.

        Preserves the directory structure from the input directory.

        Args:
            html_file_path: Path to the source HTML file

        Returns:
            Output filename with path (without extension)
        """
        # Try to extract relative path from the file path
        try:
            rel_path = html_file_path.relative_to(Path(self.input_dir))
            parts = rel_path.parts

            # If there are multiple parts in the path, preserve the structure
            if len(parts) >= MIN_NESTED_PATH_PARTS:
                # Preserve the original directory structure but replace .html extension
                return str(rel_path).replace(".html", "")
        except ValueError:
            # If the file is not in the input directory, just use its name
            return html_file_path.stem
        else:
            # Just use filename if there's only one part
            return html_file_path.stem

    def _save_markdown(
        self,
        filename: str,
        title: str,
        content: str,
        metadata: dict[str, Any],
    ) -> str:
        """Save content as a markdown file with YAML frontmatter.

        Args:
            filename: Base filename (without extension)
            title: Content title
            content: Markdown content
            metadata: Dictionary of metadata

        Returns:
            Path to the saved file
        """
        # Ensure filename has .md extension
        if not filename.endswith(".md"):
            filename = f"{filename}.md"

        # Create the full output path
        output_path = Path(self.output_dir) / filename

        # Create parent directories if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Prepare the markdown content with frontmatter
        frontmatter = yaml.dump(metadata, default_flow_style=False)
        markdown_content = f"---\n{frontmatter}---\n\n# {title}\n\n{content}\n"

        # Save the file
        with output_path.open("w", encoding="utf-8") as f:
            f.write(markdown_content)

        self.logger.info("Saved markdown to %s", output_path)
        return str(output_path)

    def parse_all(self) -> list[dict[str, Any]]:
        """Parse all HTML files in the configured site's directory.

        This parser is focused on processing only files within the specific
        domain directory defined in the configuration.

        Returns:
            List of dictionaries containing information about parsed files
        """
        self.logger.info(
            "Parsing HTML files for site '%s' from directory '%s'",
            self.site,
            self.input_dir,
        )

        # Create a directory scope for processing only files in the site's directory
        with self._create_directory_scope() as scoped_dir:
            results: list[dict[str, Any]] = []

            # Get all HTML files
            html_dir = scoped_dir

            # Find all HTML files recursively
            html_files = list(Path(html_dir).rglob("*.html"))

            self.logger.info("Found %d HTML files to parse", len(html_files))

            # Parse each file with URL context preservation
            for html_file in html_files:
                try:
                    result = self._parse_file_with_context(html_file)
                    if result:
                        results.append(result)
                except Exception:
                    self.logger.exception("Error parsing %s", html_file)

            # Create an index file for all parsed files
            if results:
                self._create_index(results)

            self.logger.info("Parsed %d files", len(results))
            return results

    def _create_index(self, results: list[dict[str, Any]]) -> str:
        """Create an index markdown file for all parsed content.

        Args:
            results: List of parsing results

        Returns:
            Path to the index file
        """
        index_path = Path(self.output_dir) / "index.md"

        with index_path.open("w", encoding="utf-8") as f:
            f.write(f"# {self.site or 'Site'} Parsed Content Index\n\n")
            f.write(f"Total pages parsed: {len(results)}\n\n")
            f.write("| Title | Source File | Output File |\n")
            f.write("|-------|-------------|-------------|\n")

            for result in results:
                title = result.get("title", "Untitled")
                source = Path(result.get("source_file", "")).name
                output = Path(result.get("output_file", "")).name

                # Create relative links to the files
                f.write(f"| {title} | {source} | [{output}]({output}) |\n")

        self.logger.info("Created index at %s", index_path)
        return str(index_path)

    @classmethod
    def list_available_site_configs(cls, config_path: str | None = None) -> list[str]:
        """List all available site configurations.

        Args:
            config_path: Optional path to custom config file

        Returns:
            List of available site configuration keys
        """
        config_manager = ConfigManager(config_path)
        return config_manager.list_available_sites()

    @classmethod
    def get_site_config(
        cls,
        site: str,
        config_path: str | None = None,
    ) -> SiteConfig | None:
        """Get detailed information about a specific site configuration.

        Args:
            site: Site to get configuration for
            config_path: Optional path to custom config file

        Returns:
            SiteParserConfig for the specified site, or None if not found
        """
        try:
            config_manager = ConfigManager(config_path)
            return config_manager.get_site_config(site)
        except ValueError:
            # Return None if site doesn't exist, to maintain backward compatibility
            return None
