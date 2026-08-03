"""Crawler module for migri-assistant.

This module contains the base crawler class and runner for crawling websites
and saving HTML content. The crawler focuses solely on retrieving and saving
HTML content without parsing or processing it.
"""

from tapio_crawler.crawler.crawler import BaseCrawler
from tapio_crawler.crawler.runner import CrawlerRunner

__all__ = ["BaseCrawler", "CrawlerRunner"]
