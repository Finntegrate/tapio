"""Tests for crawler CLI discovery commands."""

from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from tapio_crawler.cli import app
from tapio_crawler.config.config_models import SiteConfig
from tapio_crawler.crawler.crawler import RenderRunSummary
from tapio_crawler.discovery.runner import (
    DiscoveryRunSummary,
    MisconfiguredDiscoveryError,
)


def test_list_sites_displays_configured_sources() -> None:
    """The ``list-sites`` command prints every configured source site."""
    result = CliRunner().invoke(app, ["list-sites"])

    assert result.exit_code == 0
    assert "migri" in result.stdout
    assert "kela" in result.stdout


def test_crawl_reports_render_summary() -> None:
    """The ``crawl`` command prints the render summary on success."""
    site_config = SiteConfig(base_url="https://example.com")
    summary = RenderRunSummary(
        run_id="abc",
        site_name="example",
        considered=2,
        rendered=1,
        saved=1,
        eligible_total=2,
        current_total=1,
        complete=True,
    )
    runner = Mock()
    runner.run.return_value = summary

    with (
        patch("tapio_crawler.cli.ConfigManager") as config_manager_type,
        patch("tapio_crawler.cli.ManifestStore") as manifest_store_type,
        patch("tapio_crawler.cli.CrawlerRunner", return_value=runner),
    ):
        config_manager_type.return_value.get_site_config.return_value = site_config
        result = CliRunner().invoke(app, ["crawl", "example"])

    assert result.exit_code == 0
    assert "for example: complete." in result.stdout
    assert "saved 1" in result.stdout
    assert "WARNING" in result.stdout
    manifest_store_type.return_value.close.assert_called_once()


def test_discover_reports_summary() -> None:
    """The ``discover`` command prints the run summary on success."""
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


def test_discover_reports_a_cache_hit() -> None:
    """The ``discover`` command notes when the summary was served from cache."""
    site_config = SiteConfig(base_url="https://example.com")
    summary = DiscoveryRunSummary(
        run_id="abc",
        site_name="example",
        discovered=2,
        eligible=1,
        excluded_by_reason={"domain_not_allowed": 1},
        child_sitemaps_fetched=0,
        complete=True,
        cached=True,
    )
    runner = Mock()
    runner.run = AsyncMock(return_value=summary)

    with (
        patch("tapio_crawler.cli.ConfigManager") as config_manager_type,
        patch("tapio_crawler.cli.ManifestStore"),
        patch("tapio_crawler.cli.DiscoveryRunner", return_value=runner),
    ):
        config_manager_type.return_value.get_site_config.return_value = site_config
        result = CliRunner().invoke(app, ["discover", "example"])

    assert result.exit_code == 0
    assert "cache hit" in result.stdout


def test_discover_exits_with_error_on_misconfiguration() -> None:
    """The ``discover`` command exits with code 1 and the error message when
    the site has no way to discover URLs.
    """
    site_config = SiteConfig(base_url="https://example.com")
    runner = Mock()
    runner.run = AsyncMock(side_effect=MisconfiguredDiscoveryError("no way to discover"))

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
