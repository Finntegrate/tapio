"""Configuration manager for the Tapio application.

This module handles loading and accessing configurations
from YAML files, providing a centralized interface for configuration data throughout the application.
"""

import logging
import os

import yaml

from tapio.config.config_models import ParserConfigRegistry, SiteConfig


class ConfigManager:
    """
    Manages configuration for the Tapio application.

    Loads site-specific configurations from YAML files and provides
    an interface to access them.
    """

    def __init__(self, config_path: str | None = None):
        """
        Initialize the configuration manager.

        Args:
            config_path: Optional path to a custom configuration file.
                         If not provided, the default configuration file is used.
        """
        self.logger = logging.getLogger(__name__)
        self._config_registry = self._load_config_registry(config_path)

    def _load_config_registry(self, config_path: str | None = None) -> ParserConfigRegistry:
        """
        Load site configuration registry from YAML.

        Args:
            config_path: Optional path to a custom configuration file.
                         If not provided, the default configuration file is used.

        Returns:
            ParserConfigRegistry containing all site configurations

        Raises:
            FileNotFoundError: If the configuration file doesn't exist
            yaml.YAMLError: If the YAML is invalid
            ValueError: If the configuration is invalid
        """
        # Default config path is in the same directory as this file
        if not config_path:
            config_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(config_dir, "site_configs.yaml")

        try:
            with open(config_path, encoding="utf-8") as file:
                config_data = yaml.safe_load(file)
                return ParserConfigRegistry(**config_data)
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {config_path}")
            raise
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML in configuration file: {e}")
            raise
        except ValueError as e:
            self.logger.error(f"Invalid configuration: {e}")
            raise

    def get_site_config(self, site: str) -> SiteConfig:
        """
        Get configuration for a specific site.

        Args:
            site: Site identifier to get configuration for

        Returns:
            SiteParserConfig for the specified site

        Raises:
            ValueError: If the site doesn't exist in the configuration
        """
        if site not in self._config_registry.sites:
            raise ValueError(f"Site '{site}' not found in configuration")

        return self._config_registry.sites[site]

    def list_available_sites(self) -> list[str]:
        """
        List all available site configurations.

        Returns:
            List of site identifiers
        """
        return list(self._config_registry.sites.keys())

    def get_site_descriptions(self) -> dict[str, str]:
        """
        Get descriptions for all available sites.

        Returns:
            Dictionary mapping site identifiers to their descriptions
        """
        return {
            site_id: site_config.description or f"Configuration for {site_id}"
            for site_id, site_config in self._config_registry.sites.items()
        }

    @classmethod
    def from_file(cls, config_path: str) -> ConfigManager:
        """
        Create a ConfigManager instance from a specific configuration file.

        Args:
            config_path: Path to the configuration file

        Returns:
            ConfigManager instance
        """
        return cls(config_path=config_path)
