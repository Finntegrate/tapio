"""Tests for the Tapio CLI commands."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tapio.cli import app


def make_fake_site_config(
    base_url: str = "https://migri.fi",
    description: str = "Finnish Immigration Service",
    max_depth: int = 2,
    limit: int = 100,
    render: bool = True,
    source: str = "all",
) -> SimpleNamespace:
    """Build a fake SiteConfig that behaves like the real thing for CLI tests.

    Uses SimpleNamespace so setting attributes (as the crawl command does with
    --depth/--limit overrides) actually works.
    """
    crawler_config = SimpleNamespace(
        max_depth=max_depth,
        limit=limit,
        render=render,
        source=source,
    )
    return SimpleNamespace(
        base_url=base_url,
        description=description,
        crawler_config=crawler_config,
    )


class TestListSitesCommand:
    """Tests for the `list-sites` CLI command."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_list_sites_default(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_manager_class:
            manager = MagicMock()
            manager.list_available_sites.return_value = ["migri", "kela"]
            manager.get_site_config.side_effect = lambda s: make_fake_site_config(
                base_url=f"https://{s}.example.com",
                description=f"{s} description",
            )
            mock_manager_class.return_value = manager

            result = self.runner.invoke(app, ["list-sites"])

        assert result.exit_code == 0
        assert "Found 2 site configurations" in result.stdout
        assert "migri" in result.stdout
        assert "kela" in result.stdout

    def test_list_sites_empty(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_manager_class:
            manager = MagicMock()
            manager.list_available_sites.return_value = []
            mock_manager_class.return_value = manager

            result = self.runner.invoke(app, ["list-sites"])

        assert result.exit_code == 0
        assert "No sites found" in result.stdout

    def test_list_sites_verbose(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_manager_class:
            manager = MagicMock()
            manager.list_available_sites.return_value = ["migri"]
            manager.get_site_config.return_value = make_fake_site_config(
                base_url="https://migri.fi",
                description="Finnish Immigration Service",
            )
            mock_manager_class.return_value = manager

            result = self.runner.invoke(app, ["list-sites", "--verbose"])

        assert result.exit_code == 0
        assert "migri.fi" in result.stdout
        assert "depth=2" in result.stdout
        assert "limit=100" in result.stdout
        assert "render=True" in result.stdout


class TestInfoCommand:
    """Tests for the `info` CLI command."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_info_prints_config(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_manager_class:
            manager = MagicMock()
            manager.get_site_config.return_value = make_fake_site_config()
            mock_manager_class.return_value = manager

            result = self.runner.invoke(app, ["info", "migri"])

        assert result.exit_code == 0
        assert "migri" in result.stdout
        assert "Max depth: 2" in result.stdout
        assert "Limit: 100" in result.stdout
        assert "Render JavaScript: True" in result.stdout
        assert "Source: all" in result.stdout

    def test_info_missing_site_returns_error(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_manager_class:
            manager = MagicMock()
            manager.get_site_config.side_effect = ValueError("Site 'unknown' not found")
            mock_manager_class.return_value = manager

            result = self.runner.invoke(app, ["info", "unknown"])

        assert result.exit_code == 1


class TestCrawlCommand:
    """Tests for the `crawl` CLI command."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_crawl_invokes_runner(self) -> None:
        cfg = make_fake_site_config()

        with (
            patch("tapio.cli.ConfigManager") as mock_manager_class,
            patch("tapio.cli.CrawlerRunner") as mock_runner_class,
        ):
            manager = MagicMock()
            manager.get_site_config.return_value = cfg
            mock_manager_class.return_value = manager

            runner_instance = MagicMock()
            runner_instance.run.return_value = [{"url": "x"}, {"url": "y"}]
            mock_runner_class.return_value = runner_instance

            result = self.runner.invoke(app, ["crawl", "migri"])

        assert result.exit_code == 0
        runner_instance.run.assert_called_once_with("migri", cfg)
        assert "Processed 2 pages" in result.stdout

    def test_crawl_with_overrides(self) -> None:
        cfg = make_fake_site_config()

        with (
            patch("tapio.cli.ConfigManager") as mock_manager_class,
            patch("tapio.cli.CrawlerRunner") as mock_runner_class,
        ):
            manager = MagicMock()
            manager.get_site_config.return_value = cfg
            mock_manager_class.return_value = manager

            runner_instance = MagicMock()
            runner_instance.run.return_value = []
            mock_runner_class.return_value = runner_instance

            result = self.runner.invoke(app, ["crawl", "migri", "--depth", "3", "--limit", "50", "--no-render"])

        assert result.exit_code == 0
        assert cfg.crawler_config.max_depth == 3
        assert cfg.crawler_config.limit == 50
        assert cfg.crawler_config.render is False

    def test_crawl_missing_site_returns_error(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_manager_class:
            manager = MagicMock()
            manager.get_site_config.side_effect = ValueError("Site 'unknown' not found")
            mock_manager_class.return_value = manager

            result = self.runner.invoke(app, ["crawl", "unknown"])

        assert result.exit_code == 1