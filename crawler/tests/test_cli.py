"""Tests for crawler CLI discovery commands."""

from typer.testing import CliRunner

from tapio_crawler.cli import app


def test_list_sites_displays_configured_sources() -> None:
    result = CliRunner().invoke(app, ["list-sites"])

    assert result.exit_code == 0
    assert "migri" in result.stdout
    assert "kela" in result.stdout
