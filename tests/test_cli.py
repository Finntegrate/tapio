"""Tests for the Tapio CLI commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tapio.cli import app


class TestListSitesCommand:
    """Tests for the `list-sites` CLI command."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_list_sites_default(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_config_manager:
            manager = MagicMock()
            manager.list_available_sites.return_value = ["migri", "kela"]

            def mock_get_site(site: str) -> MagicMock:
                cfg = MagicMock()
                cfg.description = f"{site} description"
                cfg.base_url = f"https://{site}.example.com"
                cfg.crawler_config.max_depth = 2
                cfg.crawler_config.limit = 100
                cfg.crawler_config.render = True
                cfg.crawler_config.source = "all"
                return cfg

            manager.get_site_config.side_effect = mock_get_site
            mock_config_manager.return_value = manager

            result = self.runner.invoke(app, ["list-sites"])

        assert result.exit_code == 0
        assert "Found 2 site configurations" in result.stdout
        assert "migri" in result.stdout
        assert "kela" in result.stdout

    def test_list_sites_empty(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_config_manager:
            manager = MagicMock()
            manager.list_available_sites.return_value = []
            mock_config_manager.return_value = manager

            result = self.runner.invoke(app, ["list-sites"])

        assert result.exit_code == 0
        assert "No sites found" in result.stdout

    def test_list_sites_verbose(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_config_manager:
            manager = MagicMock()
            manager.list_available_sites.return_value = ["migri"]

            cfg = MagicMock()
            cfg.description = "Finnish Immigration Service"
            cfg.base_url = "https://migri.fi"
            cfg.crawler_config.max_depth = 2
            cfg.crawler_config.limit = 100
            cfg.crawler_config.render = True
            cfg.crawler_config.source = "all"
            manager.get_site_config.return_value = cfg
            mock_config_manager.return_value = manager

            result = self.runner.invoke(app, ["list-sites", "--verbose"])

        assert result.exit_code == 0
        assert "Base URL" in result.stdout
        assert "migri.fi" in result.stdout


class TestInfoCommand:
    """Tests for the `info` CLI command."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_info_prints_config(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_config_manager:
            manager = MagicMock()

            cfg = MagicMock()
            cfg.description = "Finnish Immigration Service"
            cfg.base_url = "https://migri.fi"
            cfg.crawler_config.max_depth = 2
            cfg.crawler_config.limit = 100
            cfg.crawler_config.render = True
            cfg.crawler_config.source = "all"
            manager.get_site_config.return_value = cfg
            mock_config_manager.return_value = manager

            result = self.runner.invoke(app, ["info", "migri"])

        assert result.exit_code == 0
        assert "migri" in result.stdout
        assert "Max depth: 2" in result.stdout
        assert "Limit: 100" in result.stdout
        assert "Render JavaScript: True" in result.stdout
        assert "Source: all" in result.stdout

    def test_info_missing_site_returns_error(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_config_manager:
            manager = MagicMock()
            manager.get_site_config.side_effect = ValueError("Site 'unknown' not found")
            mock_config_manager.return_value = manager

            result = self.runner.invoke(app, ["info", "unknown"])

        assert result.exit_code == 1


class TestCrawlCommand:
    """Tests for the `crawl` CLI command."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_crawl_invokes_runner(self) -> None:
        with (
            patch("tapio.cli.ConfigManager") as mock_config_manager,
            patch("tapio.cli.CrawlerRunner") as mock_runner_class,
        ):
            manager = MagicMock()
            cfg = MagicMock()
            cfg.base_url = "https://migri.fi"
            cfg.crawler_config.max_depth = 2
            cfg.crawler_config.limit = 100
            cfg.crawler_config.render = True
            cfg.crawler_config.source = "all"
            manager.get_site_config.return_value = cfg
            mock_config_manager.return_value = manager

            runner_instance = MagicMock()
            runner_instance.run.return_value = [{"url": "x"}, {"url": "y"}]
            mock_runner_class.return_value = runner_instance

            result = self.runner.invoke(app, ["crawl", "migri"])

        assert result.exit_code == 0
        runner_instance.run.assert_called_once_with("migri", cfg)
        assert "Processed 2 pages" in result.stdout

    def test_crawl_with_overrides(self) -> None:
        with (
            patch("tapio.cli.ConfigManager") as mock_config_manager,
            patch("tapio.cli.CrawlerRunner") as mock_runner_class,
        ):
            manager = MagicMock()
            cfg = MagicMock()
            cfg.base_url = "https://migri.fi"
            cfg.crawler_config.max_depth = 1
            cfg.crawler_config.limit = 10
            cfg.crawler_config.render = True
            cfg.crawler_config.source = "all"
            manager.get_site_config.return_value = cfg
            mock_config_manager.return_value = manager

            runner_instance = MagicMock()
            runner_instance.run.return_value = []
            mock_runner_class.return_value = runner_instance

            result = self.runner.invoke(app, ["crawl", "migri", "--depth", "3", "--limit", "50", "--no-render"])

        assert result.exit_code == 0
        assert cfg.crawler_config.max_depth == 3
        assert cfg.crawler_config.limit == 50
        assert cfg.crawler_config.render is False

    def test_crawl_missing_site_returns_error(self) -> None:
        with patch("tapio.cli.ConfigManager") as mock_config_manager:
            manager = MagicMock()
            manager.get_site_config.side_effect = ValueError("Site 'unknown' not found")
            mock_config_manager.return_value = manager

            result = self.runner.invoke(app, ["crawl", "unknown"])

        assert result.exit_code == 1