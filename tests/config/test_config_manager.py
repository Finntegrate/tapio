"""Tests for the config manager."""

from unittest.mock import mock_open, patch

import pytest
import yaml

from tapio.config.config_manager import ConfigManager


SAMPLE_YAML_DATA = {
    "sites": {
        "test_site": {
            "base_url": "https://test.example.com",
            "description": "Test site",
            "crawler_config": {
                "max_depth": 2,
                "limit": 50,
                "render": True,
                "source": "all",
            },
        },
        "another_site": {
            "base_url": "https://another.example.com",
            "crawler_config": {
                "max_depth": 1,
                "limit": 20,
                "render": False,
                "source": "sitemaps",
            },
        },
    },
}


class TestConfigManager:
    """Behavior of ConfigManager loading site configs from YAML."""

    def _load_manager(self) -> ConfigManager:
        with patch("builtins.open", mock_open(read_data="ignored")):
            with patch("tapio.config.config_manager.yaml.safe_load", return_value=SAMPLE_YAML_DATA):
                return ConfigManager()

    def test_load_default_config(self) -> None:
        manager = self._load_manager()
        sites = manager.list_available_sites()
        assert "test_site" in sites
        assert "another_site" in sites

    def test_get_site_config(self) -> None:
        manager = self._load_manager()
        site = manager.get_site_config("test_site")

        assert str(site.base_url) == "https://test.example.com/"
        assert site.description == "Test site"
        assert site.crawler_config.max_depth == 2
        assert site.crawler_config.limit == 50
        assert site.crawler_config.render is True
        assert site.crawler_config.source == "all"

    def test_get_site_config_second_site(self) -> None:
        manager = self._load_manager()
        site = manager.get_site_config("another_site")

        assert str(site.base_url) == "https://another.example.com/"
        assert site.crawler_config.max_depth == 1
        assert site.crawler_config.limit == 20
        assert site.crawler_config.render is False
        assert site.crawler_config.source == "sitemaps"

    def test_get_unknown_site_raises_value_error(self) -> None:
        manager = self._load_manager()
        with pytest.raises(ValueError, match="not found"):
            manager.get_site_config("does_not_exist")

    def test_list_available_sites(self) -> None:
        manager = self._load_manager()
        assert sorted(manager.list_available_sites()) == ["another_site", "test_site"]

    def test_get_site_descriptions(self) -> None:
        manager = self._load_manager()
        descriptions = manager.get_site_descriptions()
        assert descriptions["test_site"] == "Test site"
        assert "another_site" in descriptions

    def test_config_file_not_found_raises(self) -> None:
        with patch("builtins.open", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                ConfigManager("nonexistent.yaml")

    def test_invalid_yaml_raises(self) -> None:
        with patch("builtins.open", mock_open(read_data="ignored")):
            with patch(
                "tapio.config.config_manager.yaml.safe_load",
                side_effect=yaml.YAMLError("bad yaml"),
            ):
                with pytest.raises(yaml.YAMLError):
                    ConfigManager()

    def test_from_file_classmethod(self) -> None:
        with patch("builtins.open", mock_open(read_data="ignored")):
            with patch("tapio.config.config_manager.yaml.safe_load", return_value=SAMPLE_YAML_DATA):
                manager = ConfigManager.from_file("custom.yaml")

        assert "test_site" in manager.list_available_sites()