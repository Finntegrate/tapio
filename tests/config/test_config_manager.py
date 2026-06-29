"""Tests for the ConfigManager class."""

from unittest.mock import mock_open, patch

import pytest
import yaml
from pydantic import ValidationError

from tapio.config import ConfigManager
from tapio.config.config_models import SiteConfig


class TestConfigManager:
    """Tests for the ConfigManager class."""

    @pytest.fixture
    def basic_config_yaml(self):
        """Fixture providing basic site configuration YAML."""
        return """
            sites:
              test_site:
                base_url: "https://example.com"
                parser_config:
                  content_selectors:
                    - "//main"
        """

    @pytest.fixture
    def multi_site_config_yaml(self):
        """Fixture providing configuration with multiple sites."""
        return """
            sites:
              site1:
                base_url: "https://site1.com"
                description: "Site 1"
                parser_config:
                  content_selectors:
                    - "//main"
              site2:
                base_url: "https://site2.com"
                description: "Site 2"
                parser_config:
                  content_selectors:
                    - "//main"
              site3:
                base_url: "https://site3.com"
                description: "Site 3"
                parser_config:
                  content_selectors:
                    - "//main"
        """

    @pytest.fixture
    def site_with_descriptions_yaml(self):
        """Fixture providing sites with description fields."""
        return """
            sites:
              site1:
                base_url: "https://site1.com"
                description: "First site description"
                parser_config:
                  content_selectors:
                    - "//main"
              site2:
                base_url: "https://site2.com"
                description: "Second site description"
                parser_config:
                  content_selectors:
                    - "//main"
              site3:
                base_url: "https://site3.com"
                parser_config:
                  content_selectors:
                    - "//main"
        """

    @pytest.fixture
    def invalid_url_config_yaml(self):
        """Fixture providing configuration with invalid URL."""
        return """
            sites:
              invalid_url_site:
                base_url: "invalid-url"
                parser_config:
                  content_selectors:
                    - "//main"
        """

    def test_init_default_path(self, basic_config_yaml):
        """Test initialization with default config path."""
        with patch(
            "pathlib.Path.open",
            mock_open(read_data=basic_config_yaml),
        ) as mock_file:
            config_manager = ConfigManager()

            # Verify the file was opened
            mock_file.assert_called()

            # Check that at least one site was loaded
            assert len(config_manager.list_available_sites()) > 0

    @pytest.fixture
    def custom_site_config_yaml(self):
        """Fixture providing custom site configuration YAML."""
        return """
            sites:
              custom_site:
                site_name: "custom"
                base_url: "https://custom-example.com"
                content_selectors:
                  - "//main"
        """

    def test_init_custom_path(self, custom_site_config_yaml):
        """Test initialization with custom config path."""
        test_config_path = "/path/to/custom/config.yaml"

        with patch("pathlib.Path.open", mock_open(read_data=custom_site_config_yaml)) as mock_file:
            config_manager = ConfigManager(config_path=test_config_path)
            mock_file.assert_called_with(encoding="utf-8")

            # Test the loaded site data
            assert "custom_site" in config_manager.list_available_sites()

    def test_from_file_class_method(self, basic_config_yaml):
        """Test the from_file class method."""
        test_config_path = "/path/to/custom/config.yaml"

        with patch("pathlib.Path.open", mock_open(read_data=basic_config_yaml)):
            config_manager = ConfigManager.from_file(test_config_path)
            assert isinstance(config_manager, ConfigManager)
            assert "test_site" in config_manager.list_available_sites()

    def test_file_not_found(self):
        """Test handling of non-existent configuration file."""
        with patch("pathlib.Path.open", side_effect=FileNotFoundError()), pytest.raises(FileNotFoundError):
            ConfigManager(config_path="nonexistent_file.yaml")

    def test_invalid_yaml(self):
        """Test handling of invalid YAML file."""
        with (
            patch("pathlib.Path.open", mock_open(read_data=": invalid: yaml: content")),
            patch("yaml.safe_load", side_effect=yaml.YAMLError("Invalid YAML")),
            pytest.raises(yaml.YAMLError),
        ):
            ConfigManager(config_path="invalid_yaml.yaml")

    def test_invalid_config_structure(self):
        """Test handling of invalid configuration structure."""
        with patch("pathlib.Path.open", mock_open(read_data="not_sites: {}")), pytest.raises(ValidationError):
            ConfigManager(config_path="invalid_structure.yaml")

    def test_get_site_config(self, basic_config_yaml):
        """Test retrieving a specific site configuration."""
        with patch(
            "pathlib.Path.open",
            mock_open(read_data=basic_config_yaml),
        ):
            config_manager = ConfigManager()
            site_config = config_manager.get_site_config("test_site")
            assert isinstance(site_config, SiteConfig)
            assert str(site_config.base_url) == "https://example.com/"
            assert "//main" in site_config.parser_config.content_selectors

    def test_get_nonexistent_site_config(self, basic_config_yaml):
        """Test retrieving a non-existent site configuration."""
        with patch(
            "pathlib.Path.open",
            mock_open(read_data=basic_config_yaml),
        ):
            config_manager = ConfigManager()
            with pytest.raises(ValueError, match="Site 'nonexistent' not found in configuration"):
                config_manager.get_site_config("nonexistent")

    def test_get_site_with_invalid_url(self, invalid_url_config_yaml):
        """Test retrieving site configuration with invalid base_url."""
        # Now the validation happens at model creation time via Pydantic
        with (
            patch("pathlib.Path.open", mock_open(read_data=invalid_url_config_yaml)),
            pytest.raises(ValidationError),
        ):
            _ = ConfigManager()

    def test_list_available_sites(self, multi_site_config_yaml):
        """Test listing all available site configurations."""
        with patch("pathlib.Path.open", mock_open(read_data=multi_site_config_yaml)):
            config_manager = ConfigManager()
            available_sites = config_manager.list_available_sites()
            assert len(available_sites) == 3
            assert "site1" in available_sites
            assert "site2" in available_sites
            assert "site3" in available_sites

    def test_get_site_descriptions(self, site_with_descriptions_yaml):
        """Test getting descriptions for all site configurations."""
        with patch("pathlib.Path.open", mock_open(read_data=site_with_descriptions_yaml)):
            config_manager = ConfigManager()
            site_descriptions = config_manager.get_site_descriptions()

            assert len(site_descriptions) == 3
            assert site_descriptions["site1"] == "First site description"
            assert site_descriptions["site2"] == "Second site description"
            # Test that default description is generated for sites without a description
            assert site_descriptions["site3"] == "Configuration for site3"
