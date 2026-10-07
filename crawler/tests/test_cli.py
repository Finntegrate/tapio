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
        robots_txt_url="https://example.com/robots.txt",
        sitemap_urls=["https://example.com/sitemap.xml"],
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
    assert "https://example.com/robots.txt" in result.stdout
    assert "https://example.com/sitemap.xml" in result.stdout
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


def _fake_run_jobs(recorder: dict[str, object], *, phase: str = "done", fail: bool = False) -> AsyncMock:
    async def fake(jobs: list, **kwargs: object) -> None:
        recorder["kwargs"] = kwargs
        recorder["sites"] = [job.site_name for job in jobs]
        for job in jobs:
            job.progress.phase = phase
            if fail:
                job.error = RuntimeError("boom")
            else:
                job.render = RenderRunSummary(
                    run_id="r",
                    site_name=job.site_name,
                    saved=1,
                    eligible_total=2,
                    current_total=1,
                )

    return AsyncMock(side_effect=fake)


def _invoke_with_fake(args: list[str], **fake_options: object) -> tuple[object, dict[str, object]]:
    recorder: dict[str, object] = {}
    with (
        patch("tapio_crawler.cli.ConfigManager") as config_manager_type,
        patch("tapio_crawler.cli.run_jobs", _fake_run_jobs(recorder, **fake_options)),
    ):
        config_manager_type.return_value.list_available_sites.return_value = ["a", "b"]
        config_manager_type.return_value.get_site_config.return_value = SiteConfig(base_url="https://example.com")
        result = CliRunner().invoke(app, args)
    return result, recorder


def test_run_all_defaults_to_every_configured_site() -> None:
    """``run-all`` with no sites runs every configured site as a full job."""
    result, recorder = _invoke_with_fake(["run-all", "--max-concurrent-sites", "2"])

    assert result.exit_code == 0
    assert recorder["sites"] == ["a", "b"]
    assert recorder["kwargs"]["mode"] == "full"
    assert recorder["kwargs"]["max_concurrent_sites"] == 2
    assert "[a] done" in result.stdout
    assert "[b] done" in result.stdout


def test_run_all_accepts_an_explicit_site_subset() -> None:
    """Named sites narrow the run."""
    result, recorder = _invoke_with_fake(["run-all", "b"])

    assert result.exit_code == 0
    assert recorder["sites"] == ["b"]


def test_run_all_exits_nonzero_when_a_site_job_fails() -> None:
    """A failed job is reported and makes the invocation fail."""
    result, _ = _invoke_with_fake(["run-all"], phase="failed", fail=True)

    assert result.exit_code == 1
    assert "[a] FAILED: boom" in result.stdout


def test_run_all_exits_130_when_cancelled() -> None:
    """A cancelled run exits with the conventional interrupt status."""
    result, _ = _invoke_with_fake(["run-all"], phase="cancelled")

    assert result.exit_code == 130


def test_run_all_reports_resource_peak_when_asked() -> None:
    """``--report-resources`` appends a peak memory/CPU line."""
    result, _ = _invoke_with_fake(["run-all", "--report-resources"])

    assert result.exit_code == 0
    assert "Resources: peak" in result.stdout


def test_retry_runs_in_retry_mode_without_discovery() -> None:
    """``retry`` selects retry mode and forwards ``--include-inactive``."""
    result, recorder = _invoke_with_fake(["retry", "a", "--include-inactive"])

    assert result.exit_code == 0
    assert recorder["kwargs"]["mode"] == "retry"
    assert recorder["kwargs"]["include_inactive"] is True


def test_run_all_with_no_configured_sites_exits_with_error() -> None:
    """An empty site list is an error rather than a silent no-op."""
    with patch("tapio_crawler.cli.ConfigManager") as config_manager_type:
        config_manager_type.return_value.list_available_sites.return_value = []
        result = CliRunner().invoke(app, ["run-all"])

    assert result.exit_code == 1
    assert "No crawler sites are configured." in result.stdout


def test_run_all_deduplicates_repeated_site_names() -> None:
    """Naming a site twice runs it once, so two jobs never write the same records."""
    result, recorder = _invoke_with_fake(["run-all", "a", "a", "b"])

    assert result.exit_code == 0
    assert recorder["sites"] == ["a", "b"]


def test_run_all_rejects_non_positive_batch_size_and_interval() -> None:
    """Zero or negative values are rejected at the CLI boundary."""
    assert CliRunner().invoke(app, ["run-all", "--batch-size", "0"]).exit_code != 0
    assert CliRunner().invoke(app, ["retry", "--progress-interval", "0"]).exit_code != 0


def test_run_all_exits_nonzero_when_a_job_is_incomplete() -> None:
    """An incomplete run (for example robots.txt unreachable) must not exit 0."""
    result, _ = _invoke_with_fake(["run-all"], phase="incomplete")

    assert result.exit_code == 1
