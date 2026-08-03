"""Tests for crawler CLI discovery commands."""

from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from tapio_crawler.cli import app, crawl
from tapio_crawler.config.config_models import SiteConfig


def test_list_sites_displays_configured_sources() -> None:
    result = CliRunner().invoke(app, ["list-sites"])

    assert result.exit_code == 0
    assert "migri" in result.stdout
    assert "kela" in result.stdout


def test_crawl_raises_when_the_runner_does_not_provide_a_summary() -> None:
    """Fail clearly when a completed crawl has no execution summary."""
    site_config = SiteConfig(base_url="https://example.com")
    runner = Mock()
    runner.run.return_value = []
    runner.last_summary = None

    with (
        patch("tapio_crawler.cli.ConfigManager") as config_manager_type,
        patch("tapio_crawler.cli.CrawlerRunner", return_value=runner),
        pytest.raises(RuntimeError, match="^Crawler finished without a summary\\.$"),
    ):
        config_manager_type.return_value.get_site_config.return_value = site_config
        crawl("example", depth=None, force=False)
