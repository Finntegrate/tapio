"""Tests for crawler CLI discovery commands."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from typer.testing import CliRunner

from tapio_crawler.cli import app, crawl
from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.discovery.runner import (
    DiscoveryRunSummary,
    MisconfiguredDiscoveryError,
)


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


def test_discover_reports_summary() -> None:
    site_config = SiteConfig(base_url="https://example.com")
    summary = DiscoveryRunSummary(
        run_id="abc",
        site_name="example",
        discovered=2,
        eligible=1,
        excluded_by_reason={"domain_not_allowed": 1},
        child_sitemaps_fetched=1,
        complete=True,
    )
    runner = Mock()
    runner.run = AsyncMock(return_value=summary)

    with (
        patch("tapio_crawler.cli.ConfigManager") as config_manager_type,
        patch("tapio_crawler.cli.ManifestStore") as manifest_store_type,
        patch("tapio_crawler.cli.DiscoveryRunner", return_value=runner),
    ):
        config_manager_type.return_value.get_site_config.return_value = site_config
        result = CliRunner().invoke(app, ["discover", "example"])

    assert result.exit_code == 0
    assert "complete" in result.stdout
    assert "eligible 1" in result.stdout
    manifest_store_type.return_value.close.assert_called_once()


def test_discover_exits_with_error_on_misconfiguration() -> None:
    site_config = SiteConfig(base_url="https://example.com")
    runner = Mock()
    runner.run = AsyncMock(
        side_effect=MisconfiguredDiscoveryError("no way to discover")
    )

    with (
        patch("tapio_crawler.cli.ConfigManager") as config_manager_type,
        patch("tapio_crawler.cli.ManifestStore") as manifest_store_type,
        patch("tapio_crawler.cli.DiscoveryRunner", return_value=runner),
    ):
        config_manager_type.return_value.get_site_config.return_value = site_config
        result = CliRunner().invoke(app, ["discover", "example"])

    assert result.exit_code == 1
    assert "no way to discover" in result.stdout
    manifest_store_type.return_value.close.assert_called_once()
