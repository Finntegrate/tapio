"""Tests for the CLI module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from tapio.cli import app, find_sites_with_crawled_content
from tapio.config.settings import DEFAULT_CONTENT_DIR


@pytest.fixture
def runner():
    """Fixture for creating a CLI runner."""
    return CliRunner()


class TestCli:
    """Tests for the CLI module."""

    def test_info_command(self, runner):
        """Test the info command."""
        result = runner.invoke(app, ["info"])

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that expected output is present
        assert "Tapio Assistant" in result.stdout
        assert "Available commands:" in result.stdout
        assert "crawl" in result.stdout
        assert "parse" in result.stdout
        assert "vectorize" in result.stdout
        assert "info" in result.stdout

    @patch("tapio.cli.CrawlerRunner")
    @patch("tapio.cli.ConfigManager")
    def test_crawl_command(self, mock_config_manager, mock_crawler_runner, runner):
        """Test the crawl command."""
        # Set up mocks
        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = ["page1", "page2", "page3"]
        mock_crawler_runner.return_value = mock_runner_instance

        # Mock ConfigManager
        mock_config_instance = MagicMock()
        mock_site_config = MagicMock()
        mock_site_config.base_url = "https://example.com"
        mock_site_config.base_dir = "example.com"  # This should be just the domain
        # Mock the crawler_config with appropriate default values
        mock_crawler_config = MagicMock()
        mock_crawler_config.delay_between_requests = 1.0
        mock_crawler_config.max_concurrent = 5
        mock_crawler_config.depth = 1  # Add depth attribute
        mock_site_config.crawler_config = mock_crawler_config
        mock_config_instance.get_site_config.return_value = mock_site_config
        mock_config_instance.list_available_sites.return_value = ["migri"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command
        result = runner.invoke(
            app,
            [
                "crawl",
                "migri",
                "--depth",
                "2",
            ],
        )

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that list_available_sites was called
        mock_config_instance.list_available_sites.assert_called_once()

        # Check that get_site_config was called with the correct site name
        mock_config_instance.get_site_config.assert_called_once_with("migri")

        # Check that the runner was initialized correctly
        mock_crawler_runner.assert_called_once()

        # Check that run was called with the new interface
        mock_runner_instance.run.assert_called_once_with("migri", mock_site_config)

        # Check that depth was overridden
        assert mock_site_config.crawler_config.max_depth == 2

        # Check expected output in stdout
        assert "Starting web crawler" in result.stdout
        assert "Crawling completed" in result.stdout
        assert "Processed 3 pages" in result.stdout

    @patch("tapio.cli.CrawlerRunner")
    @patch("tapio.cli.ConfigManager")
    def test_crawl_command_keyboard_interrupt(self, mock_config_manager, mock_crawler_runner, runner):
        """Test handling of keyboard interrupt in crawl command."""
        # Mock ConfigManager
        mock_config_instance = MagicMock()
        mock_site_config = MagicMock()
        mock_site_config.base_url = "https://example.com"
        mock_site_config.base_dir = "example.com"
        # Mock the crawler_config
        mock_crawler_config = MagicMock()
        mock_crawler_config.delay_between_requests = 1.0
        mock_crawler_config.max_concurrent = 5
        mock_crawler_config.depth = 1
        mock_site_config.crawler_config = mock_crawler_config
        mock_config_instance.get_site_config.return_value = mock_site_config
        mock_config_instance.list_available_sites.return_value = ["migri"]
        mock_config_manager.return_value = mock_config_instance

        # Set up mock to raise KeyboardInterrupt
        mock_runner_instance = MagicMock()
        mock_runner_instance.run.side_effect = KeyboardInterrupt()
        mock_crawler_runner.return_value = mock_runner_instance

        # Run the command
        result = runner.invoke(app, ["crawl", "migri"])

        # Check that the command exited successfully (handled the interrupt)
        assert result.exit_code == 0

        # Check expected output in stdout
        assert "Starting web crawler for migri" in result.stdout
        assert "Crawling interrupted by user" in result.stdout
        assert "Partial results have been saved" in result.stdout

    @patch("tapio.cli.CrawlerRunner")
    @patch("tapio.cli.ConfigManager")
    def test_crawl_command_exception(self, mock_config_manager, mock_crawler_runner, runner):
        """Test handling of exceptions in crawl command."""
        # Mock ConfigManager
        mock_config_instance = MagicMock()
        mock_site_config = MagicMock()
        mock_site_config.base_url = "https://example.com"
        mock_site_config.base_dir = "example.com"
        # Mock the crawler_config
        mock_crawler_config = MagicMock()
        mock_crawler_config.delay_between_requests = 1.0
        mock_crawler_config.max_concurrent = 5
        mock_crawler_config.depth = 1
        mock_site_config.crawler_config = mock_crawler_config
        mock_config_instance.get_site_config.return_value = mock_site_config
        mock_config_instance.list_available_sites.return_value = ["migri"]
        mock_config_manager.return_value = mock_config_instance

        # Set up mock to raise an exception
        mock_runner_instance = MagicMock()
        mock_runner_instance.run.side_effect = Exception("Test error")
        mock_crawler_runner.return_value = mock_runner_instance

        # Run the command
        result = runner.invoke(app, ["crawl", "migri"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "Starting web crawler for migri" in result.stdout
        assert "Error during crawling: Test error" in result.output

    @patch("tapio.cli.ConfigManager")
    def test_crawl_command_invalid_site(self, mock_config_manager, runner):
        """Test the crawl command with an invalid site name."""
        # Mock the ConfigManager
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri", "te_palvelut", "kela"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command with an unsupported site
        result = runner.invoke(app, ["crawl", "unsupported_site"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "Unsupported site: unsupported_site" in result.stdout
        assert "Available sites: migri, te_palvelut, kela" in result.stdout

    @patch("tapio.cli.ConfigManager")
    @patch("tapio.cli.Parser")
    def test_parse_command(self, mock_parser, mock_config_manager, runner):
        """Test the parse command."""
        # Set up mock parser
        mock_parser_instance = MagicMock()
        mock_parser_instance.parse_all.return_value = ["file1", "file2", "file3"]
        mock_parser.return_value = mock_parser_instance

        # Set up mock config manager
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command
        result = runner.invoke(
            app,
            [
                "parse",
                "migri",
            ],
        )

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that the parser was initialized with dependency injection
        assert mock_parser.call_count == 1
        call_kwargs = mock_parser.call_args[1]
        assert call_kwargs["site_name"] == "migri"
        assert "site_config" in call_kwargs
        assert "input_dir" in call_kwargs
        assert "output_dir" in call_kwargs

        # Check that list_available_sites was called
        mock_config_instance.list_available_sites.assert_called_once()

        # Check that parse_all was called correctly (without domain parameter)
        mock_parser_instance.parse_all.assert_called_once_with()

        # Check expected output in stdout
        assert "Starting HTML parsing" in result.stdout
        assert "Using configuration for site: migri" in result.stdout
        assert "Parsing completed" in result.stdout
        assert "Processed 3 files" in result.stdout

    @patch("tapio.cli.ConfigManager")
    def test_parse_command_unsupported_site(self, mock_config_manager, runner):
        """Test the parse command with an unsupported site."""
        # Set up mock config manager
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri", "te_palvelut", "kela"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command with an unsupported site
        result = runner.invoke(app, ["parse", "unsupported"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "Unsupported site: unsupported" in result.stdout
        assert "Available sites: migri, te_palvelut, kela" in result.stdout

        # Check that list_available_sites was called
        mock_config_instance.list_available_sites.assert_called_once()

    @patch("tapio.cli.ConfigManager")
    @patch("tapio.cli.Parser")
    def test_parse_command_exception(self, mock_parser, mock_config_manager, runner):
        """Test handling of exceptions in parse command."""
        # Set up mock parser that raises an exception
        mock_parser_instance = MagicMock()
        mock_parser_instance.parse_all.side_effect = Exception("Test error")
        mock_parser.return_value = mock_parser_instance

        # Set up mock config manager
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command
        result = runner.invoke(app, ["parse", "migri"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "Starting HTML parsing" in result.stdout
        assert "Error during parsing: Test error" in result.output

        # Check that list_available_sites was called
        mock_config_instance.list_available_sites.assert_called_once()

    @patch("tapio.cli.ConfigManager")
    @patch("tapio.cli.Parser")
    @patch("os.path.exists")
    def test_parse_command_custom_config(self, mock_exists, mock_parser, mock_config_manager, runner):
        """Test the parse command with a custom config path."""
        # Setup mock for file existence check
        mock_exists.return_value = True

        # Set up mock parser
        mock_parser_instance = MagicMock()
        mock_parser_instance.parse_all.return_value = ["file1", "file2"]
        mock_parser.return_value = mock_parser_instance

        # Set up mock config manager
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["custom_site"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command with a custom config
        result = runner.invoke(
            app,
            [
                "parse",
                "custom_site",
                "--config",
                "custom_configs.yaml",
            ],
        )

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that ConfigManager was instantiated with the correct custom config path
        mock_config_manager.assert_called_with("custom_configs.yaml")

        # Check that list_available_sites was called
        mock_config_instance.list_available_sites.assert_called_once()

        # Check that the parser was initialized with dependency injection
        assert mock_parser.call_count == 1
        call_kwargs = mock_parser.call_args[1]
        assert call_kwargs["site_name"] == "custom_site"
        assert "site_config" in call_kwargs
        assert "input_dir" in call_kwargs
        assert "output_dir" in call_kwargs

        # Check that parse_all was called correctly (without domain parameter)
        mock_parser_instance.parse_all.assert_called_once_with()

    @patch("tapio.cli.MarkdownVectorizer")
    def test_vectorize_command_exception(self, mock_vectorizer, runner):
        """Test handling of exceptions in vectorize command."""
        # Set up mock to raise an exception
        mock_vectorizer_instance = MagicMock()
        mock_vectorizer_instance.process_directory.side_effect = Exception("Test error")
        mock_vectorizer.return_value = mock_vectorizer_instance

        # Run the command
        result = runner.invoke(app, ["vectorize"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "Starting vectorization" in result.stdout
        assert "Error during vectorization: Test error" in result.output

    @patch("tapio.cli.tapio_app")
    def test_dev_command(self, mock_tapio_app, runner):
        """Test the dev command."""
        # Run the command
        result = runner.invoke(app, ["dev"])

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that tapio_app was called correctly
        mock_tapio_app.assert_called_once_with(
            model_name="llama3.2",
            share=False,
        )

        # Check expected output in stdout
        assert "Launching Tapio Assistant chatbot development server" in result.stdout

    @patch("tapio.cli.ConfigManager")
    def test_list_sites_command(self, mock_config_manager, runner):
        """Test the list-sites command."""
        # Set up mock config manager
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri", "te_palvelut", "kela"]
        mock_config_instance.get_site_descriptions.return_value = {
            "migri": "Finnish Immigration Service",
            "te_palvelut": "Employment Services",
            "kela": "Social Insurance Institution",
        }
        mock_config_manager.return_value = mock_config_instance

        # Run the command
        result = runner.invoke(app, ["list-sites"])

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that list_available_sites was called
        mock_config_instance.list_available_sites.assert_called_once()

        # Check that get_site_descriptions was called (may be called multiple times)
        assert mock_config_instance.get_site_descriptions.called

        # Check expected output in stdout
        assert "Available Site Configurations:" in result.stdout
        assert "migri" in result.stdout
        assert "te_palvelut" in result.stdout
        assert "kela" in result.stdout
        assert "Finnish Immigration Service" in result.stdout

    @patch("tapio.cli.ConfigManager")
    def test_list_sites_command_verbose(self, mock_config_manager, runner):
        """Test the list-sites command with verbose flag."""
        # Set up mock config manager
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri"]

        # Mock site config
        mock_site_config = MagicMock()
        mock_site_config.description = "Finnish Immigration Service"

        # Mock parser config within site config
        mock_parser_config = MagicMock()
        mock_parser_config.title_selector = "h1"
        mock_parser_config.content_selectors = ["main", "article"]
        mock_parser_config.fallback_to_body = True
        mock_site_config.parser_config = mock_parser_config

        mock_config_instance.get_site_config.return_value = mock_site_config
        mock_config_manager.return_value = mock_config_instance

        # Run the command with verbose flag
        result = runner.invoke(app, ["list-sites", "--verbose"])

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that list_available_sites was called
        mock_config_instance.list_available_sites.assert_called_once()

        # Check that get_site_config was called with the right site
        mock_config_instance.get_site_config.assert_called_with("migri")

        # Check expected output in stdout
        assert "Available Site Configurations:" in result.stdout
        assert "Description: Finnish Immigration Service" in result.stdout
        assert "Title selector: h1" in result.stdout
        assert "Content selectors:" in result.stdout
        assert "Fallback to body: True" in result.stdout

    @patch("tapio.cli.ConfigManager")
    def test_list_sites_command_exception(self, mock_config_manager, runner):
        """Test handling of exceptions in list-sites command."""
        # Set up mock to raise an exception
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.side_effect = Exception("Test error")
        mock_config_manager.return_value = mock_config_instance

        # Run the command
        result = runner.invoke(app, ["list-sites"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "Error listing site configurations: Test error" in result.output

    @patch("tapio.cli.ConfigManager")
    @patch("tapio.cli.Parser")
    @patch("pathlib.Path.exists", autospec=True)
    @patch("pathlib.Path.iterdir", autospec=True)
    @patch("pathlib.Path.is_dir", autospec=True)
    @patch("pathlib.Path.rglob", autospec=True)
    def test_parse_command_no_site_specified(
        self,
        mock_rglob,
        mock_is_dir,
        mock_iterdir,
        mock_exists,
        mock_parser,
        mock_config_manager,
        runner,
    ):
        """Test the parse command when no site is specified - should parse all available sites with crawled content."""
        # Setup mocks for directory structure - new structure uses content/site_name/crawled/
        mock_exists.return_value = True
        mock_iterdir.return_value = [Path("migri"), Path("kela"), Path("vero"), Path("parsed")]
        mock_is_dir.side_effect = lambda self: not str(self).endswith(".json")

        # Mock Path.rglob to return HTML files for each site's crawled directory
        def mock_rglob_side_effect(self, _pattern):
            path_str = str(self)
            if "migri/crawled" in path_str:
                return iter([Path("page1.html"), Path("page2.html")])
            if "kela/crawled" in path_str:
                return iter([Path("page3.html")])
            if "vero/crawled" in path_str:
                return iter([Path("page4.html"), Path("page5.html")])
            return iter([])

        mock_rglob.side_effect = mock_rglob_side_effect

        # Set up mock parser instances
        mock_parser_instances = []
        for i in range(3):  # For 3 sites
            mock_instance = MagicMock()
            mock_instance.parse_all.return_value = [f"file{i * 2 + 1}", f"file{i * 2 + 2}"]
            mock_parser_instances.append(mock_instance)

        mock_parser.side_effect = mock_parser_instances

        # Set up mock config manager - sites match crawled site directories directly
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri", "kela", "vero"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command without --site parameter
        result = runner.invoke(app, ["parse"])

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that all three parsers were created
        assert mock_parser.call_count == 3

        # Check expected calls to Parser constructor - new DI format uses site_name, site_config, input_dir, output_dir
        expected_sites = ["migri", "kela", "vero"]

        for i, site_name in enumerate(expected_sites):
            assert mock_parser.call_args_list[i][1]["site_name"] == site_name
            # With DI, we pass site_config not config_path
            assert "site_config" in mock_parser.call_args_list[i][1]
            assert "input_dir" in mock_parser.call_args_list[i][1]
            assert "output_dir" in mock_parser.call_args_list[i][1]

        # Check that parse_all was called for each parser
        for mock_instance in mock_parser_instances:
            mock_instance.parse_all.assert_called_once_with()

        # Check expected output in stdout
        assert "No site specified, parsing all available sites with crawled content" in result.stdout
        assert "Found crawled content for sites: migri, kela, vero" in result.stdout
        assert "Parsing sites: migri, kela, vero" in result.stdout
        assert "Parsing site: migri" in result.stdout
        assert "Parsing site: kela" in result.stdout
        assert "Parsing site: vero" in result.stdout
        assert "All parsing completed! Processed 6 files total." in result.stdout
        assert "Parsed 3 sites: migri, kela, vero" in result.stdout

    @patch("tapio.cli.ConfigManager")
    @patch("pathlib.Path.exists", autospec=True)
    def test_parse_command_no_site_crawled_dir_not_found(self, mock_exists, mock_config_manager, runner):
        """Test the parse command when no site is specified and crawled directory doesn't exist."""
        # Setup mocks
        mock_exists.return_value = False

        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri", "kela"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command without --site parameter
        result = runner.invoke(app, ["parse"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "No site specified, parsing all available sites with crawled content" in result.stdout
        assert f"Content directory not found: {DEFAULT_CONTENT_DIR}" in result.stdout

    @patch("tapio.cli.ConfigManager")
    @patch("pathlib.Path.exists", autospec=True)
    @patch("pathlib.Path.iterdir", autospec=True)
    @patch("pathlib.Path.is_dir", autospec=True)
    @patch("pathlib.Path.rglob", autospec=True)
    def test_parse_command_no_site_no_crawled_content(
        self,
        mock_rglob,
        mock_is_dir,
        mock_iterdir,
        mock_exists,
        mock_config_manager,
        runner,
    ):
        """Test the parse command when no site is specified and no crawled content is found."""
        # Setup mocks - directory exists but contains no HTML files
        mock_exists.return_value = True
        mock_iterdir.return_value = [Path("url_mappings.json"), Path("empty_dir")]
        mock_is_dir.side_effect = lambda self: not str(self).endswith(".json")

        # Mock Path.rglob to return no HTML files
        mock_rglob.return_value = iter([])

        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri", "kela"]
        mock_config_manager.return_value = mock_config_instance

        # Run the command without --site parameter
        result = runner.invoke(app, ["parse"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "No site specified, parsing all available sites with crawled content" in result.stdout
        assert "No crawled content found to parse" in result.stdout

    @patch("tapio.cli.ConfigManager")
    @patch("pathlib.Path.exists", autospec=True)
    @patch("pathlib.Path.iterdir", autospec=True)
    @patch("pathlib.Path.is_dir", autospec=True)
    @patch("pathlib.Path.rglob", autospec=True)
    def test_parse_command_no_site_no_matching_configs(
        self,
        mock_rglob,
        mock_is_dir,
        mock_iterdir,
        mock_exists,
        mock_config_manager,
        runner,
    ):
        """Test the parse command when crawled content exists but no site configs match."""
        # Setup mocks for new directory structure - content/site_name/crawled/
        mock_exists.return_value = True
        mock_iterdir.return_value = [Path("unknown_site"), Path("another_unknown")]
        mock_is_dir.side_effect = lambda self: not str(self).endswith(".json")

        # Mock Path.rglob to return HTML files for unknown sites
        def mock_rglob_side_effect(self, _pattern):
            path_str = str(self)
            if "unknown_site/crawled" in path_str:
                return iter([Path("page1.html")])
            if "another_unknown/crawled" in path_str:
                return iter([Path("page2.html")])
            return iter([])

        mock_rglob.side_effect = mock_rglob_side_effect

        # Set up mock config manager with sites that don't match the crawled sites
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri", "kela"]

        mock_config_manager.return_value = mock_config_instance

        # Run the command without --site parameter
        result = runner.invoke(app, ["parse"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "No site specified, parsing all available sites with crawled content" in result.stdout
        expected_sites = "Crawled sites: unknown_site, another_unknown"
        assert expected_sites in result.stdout
        assert "No site configurations found matching crawled content" in result.stdout
        assert "Available sites: migri, kela" in result.stdout

    @patch("tapio.cli.ConfigManager")
    @patch("tapio.cli.Parser")
    @patch("pathlib.Path.exists", autospec=True)
    @patch("pathlib.Path.iterdir", autospec=True)
    @patch("pathlib.Path.is_dir", autospec=True)
    @patch("pathlib.Path.rglob", autospec=True)
    def test_parse_command_no_site_partial_match(
        self,
        mock_rglob,
        mock_is_dir,
        mock_iterdir,
        mock_exists,
        mock_parser,
        mock_config_manager,
        runner,
    ):
        """Test the parse command when only some crawled sites have matching site configs."""
        # Setup mocks for directory structure - new structure uses content/site_name/crawled/
        mock_exists.return_value = True
        mock_iterdir.return_value = [Path("migri"), Path("unknown"), Path("kela")]
        mock_is_dir.side_effect = lambda self: not str(self).endswith(".json")

        # Mock Path.rglob to return HTML files
        def mock_rglob_side_effect(self, _pattern):
            path_str = str(self)
            if "migri/crawled" in path_str:
                return iter([Path("page1.html")])
            if "kela/crawled" in path_str:
                return iter([Path("page2.html")])
            if "unknown/crawled" in path_str:
                return iter([Path("page3.html")])
            return iter([])

        mock_rglob.side_effect = mock_rglob_side_effect

        # Set up mock parser instances for 2 matching sites
        mock_parser_instances = []
        for i in range(2):
            mock_instance = MagicMock()
            mock_instance.parse_all.return_value = [f"file{i + 1}"]
            mock_parser_instances.append(mock_instance)

        mock_parser.side_effect = mock_parser_instances

        # Set up mock config manager - only migri and kela are available, unknown is not
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri", "kela", "vero"]

        mock_config_manager.return_value = mock_config_instance

        # Run the command without --site parameter
        result = runner.invoke(app, ["parse"])

        # Check that the command ran successfully
        assert result.exit_code == 0

        # Check that only 2 parsers were created (for migri and kela)
        assert mock_parser.call_count == 2

        # Check expected output in stdout
        assert "Found crawled content for sites: migri, unknown, kela" in result.stdout
        assert "Parsing sites: migri, kela" in result.stdout
        assert "All parsing completed! Processed 2 files total." in result.stdout
        assert "Parsed 2 sites: migri, kela" in result.stdout

    @patch("tapio.cli.ConfigManager")
    @patch("tapio.cli.Parser")
    @patch("pathlib.Path.exists", autospec=True)
    @patch("pathlib.Path.iterdir", autospec=True)
    @patch("pathlib.Path.is_dir", autospec=True)
    @patch("pathlib.Path.rglob", autospec=True)
    def test_parse_command_no_site_with_exception(
        self,
        mock_rglob,
        mock_is_dir,
        mock_iterdir,
        mock_exists,
        mock_parser,
        mock_config_manager,
        runner,
    ):
        """Test handling of exceptions in parse command when parsing all sites."""
        # Setup mocks for directory structure - new structure uses content/site_name/crawled/
        mock_exists.return_value = True
        mock_iterdir.return_value = [Path("migri")]
        mock_is_dir.side_effect = lambda self: not str(self).endswith(".json")

        def mock_rglob_side_effect(self, _pattern):
            if "migri/crawled" in str(self):
                return iter([Path("page.html")])
            return iter([])

        mock_rglob.side_effect = mock_rglob_side_effect

        # Set up mock parser that raises an exception
        mock_parser_instance = MagicMock()
        mock_parser_instance.parse_all.side_effect = Exception("Test parsing error")
        mock_parser.return_value = mock_parser_instance

        # Set up mock config manager
        mock_config_instance = MagicMock()
        mock_config_instance.list_available_sites.return_value = ["migri"]

        mock_config_manager.return_value = mock_config_instance

        # Run the command without --site parameter
        result = runner.invoke(app, ["parse"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "No site specified, parsing all available sites with crawled content" in result.stdout
        assert "Error during parsing: Test parsing error" in result.output

    @patch("tapio.cli.MarkdownVectorizer")
    def test_vectorize_command_with_nonexistent_site(self, mock_vectorizer, runner):
        """Test the vectorize command with a non-existent site."""
        # Mock Path.exists to return False for the site directory
        with patch("pathlib.Path.exists", return_value=False):
            # Run the command with non-existent site
            result = runner.invoke(app, ["vectorize", "nonexistent"])

        # Check that the command exited with error code
        assert result.exit_code == 1

        # Check expected output in stdout
        assert "No parsed content found for site: nonexistent" in result.stdout
        assert "content/nonexistent/parsed" in result.stdout

        # Verify that vectorizer was not called
        mock_vectorizer.assert_not_called()

    def test_find_sites_with_crawled_content_empty_directory(self) -> None:
        """Test find_sites_with_crawled_content with an empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = find_sites_with_crawled_content(temp_dir, "crawled")
            assert result == []

    def test_find_sites_with_crawled_content_nonexistent_directory(self) -> None:
        """Test find_sites_with_crawled_content with a nonexistent directory."""
        result = find_sites_with_crawled_content("/nonexistent/path", "crawled")
        assert result == []

    def test_find_sites_with_crawled_content_with_html_files(self) -> None:
        """Test find_sites_with_crawled_content with sites containing HTML files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a site directory structure with HTML files
            site1_dir = os.path.join(temp_dir, "site1")
            site1_crawled = os.path.join(site1_dir, "crawled")
            os.makedirs(site1_crawled)

            # Create an HTML file
            with open(os.path.join(site1_crawled, "page1.html"), "w") as f:
                f.write("<html><body>Test content</body></html>")

            # Create another site without HTML files
            site2_dir = os.path.join(temp_dir, "site2")
            site2_crawled = os.path.join(site2_dir, "crawled")
            os.makedirs(site2_crawled)

            # Create a non-HTML file
            with open(os.path.join(site2_crawled, "data.txt"), "w") as f:
                f.write("Not HTML content")

            # Create a site without crawled directory
            site3_dir = os.path.join(temp_dir, "site3")
            os.makedirs(site3_dir)

            result = find_sites_with_crawled_content(temp_dir, "crawled")

            # Only site1 should be returned since it has HTML files
            assert result == ["site1"]

    def test_find_sites_with_crawled_content_nested_html_files(self) -> None:
        """Test find_sites_with_crawled_content with HTML files in subdirectories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a site directory structure with nested HTML files
            site_dir = os.path.join(temp_dir, "test_site")
            crawled_dir = os.path.join(site_dir, "crawled")
            nested_dir = os.path.join(crawled_dir, "subdomain")
            os.makedirs(nested_dir)

            # Create an HTML file in a subdirectory
            with open(os.path.join(nested_dir, "nested_page.html"), "w") as f:
                f.write("<html><body>Nested content</body></html>")

            result = find_sites_with_crawled_content(temp_dir, "crawled")

            # The site should be found even with nested HTML files
            assert result == ["test_site"]
