"""Crawler test fixtures."""

from pathlib import Path

import pytest

from tapio_crawler.config import ConfigManager


@pytest.fixture
def test_config_manager(tmp_path: Path) -> ConfigManager:
    """A Crawl4AI site configuration isolated from repository output."""
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        """sites:
  test_site:
    base_url: https://example.com
    crawler_config:
      min_delay: 0
      max_delay: 0
""",
        encoding="utf-8",
    )
    return ConfigManager(str(config_path))
