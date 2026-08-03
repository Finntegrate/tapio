"""Crawler test fixtures."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def test_config_manager(tmp_path):
    """A site configuration isolated from the repository's crawl output."""
    from tapio_crawler.config import ConfigManager

    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        """sites:
  test_site:
    base_url: https://example.com
    crawler_config:
      max_depth: 1
      delay_between_requests: 0
      max_concurrent: 1
""",
        encoding="utf-8",
    )
    return ConfigManager(str(config_path))
