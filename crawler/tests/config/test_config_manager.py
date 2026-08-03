"""Tests for loading Crawl4AI site configuration."""

import pytest
from pydantic import ValidationError

from tapio_crawler.config import ConfigManager


def test_config_manager_loads_crawl4ai_config(tmp_path) -> None:
    path = tmp_path / "sites.yaml"
    path.write_text(
        """sites:
  example:
    base_url: https://example.com
    description: Example site
    crawler_config:
      max_depth: 0
      max_pages: 1
      min_delay: 0
      max_delay: 0
""",
        encoding="utf-8",
    )

    manager = ConfigManager.from_file(str(path))

    assert manager.list_available_sites() == ["example"]
    assert manager.get_site_config("example").crawler_config.max_depth == 0
    assert manager.get_site_descriptions() == {"example": "Example site"}


def test_config_manager_rejects_missing_base_url(tmp_path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("sites:\n  example: {}\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        ConfigManager.from_file(str(path))
