"""Parser module for tapio.

This module contains the Parser class for extracting structured content
from HTML files saved by the crawler module.
"""

from tapio.config.config_models import (
    HtmlToMarkdownConfig,
    ParserConfigRegistry,
    SiteConfig,
)
from tapio.parser.parser import Parser

__all__ = [
    "HtmlToMarkdownConfig",
    "Parser",
    "ParserConfigRegistry",
    "SiteConfig",
]
