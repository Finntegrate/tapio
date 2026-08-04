"""Configuration module for the crawler service.

This module provides configuration models and management utilities
for source-site collection and Markdown output.
"""

from tapio_crawler.config.config_manager import ConfigManager
from tapio_crawler.config.config_models import (
    CrawlerConfig,
    DiscoveryConfig,
    GapCrawlConfig,
    MarkdownConfig,
    PolitenessConfig,
    ScopeConfig,
    SiteConfig,
    SiteConfigRegistry,
)

__all__ = [
    "ConfigManager",
    "CrawlerConfig",
    "DiscoveryConfig",
    "GapCrawlConfig",
    "MarkdownConfig",
    "PolitenessConfig",
    "ScopeConfig",
    "SiteConfig",
    "SiteConfigRegistry",
]
