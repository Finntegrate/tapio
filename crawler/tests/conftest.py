"""Crawler test fixtures."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def test_config_manager(tmp_path):
    """A Crawl4AI site configuration isolated from repository output."""
    from tapio_crawler.config import ConfigManager

    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        """sites:
  test_site:
    base_url: https://example.com
    crawler_config:
      max_depth: 0
      max_pages: 1
      min_delay: 0
      max_delay: 0
""",
        encoding="utf-8",
    )
    return ConfigManager(str(config_path))
