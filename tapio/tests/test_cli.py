"""Tests for the application-only CLI surface."""

from typer.testing import CliRunner

from tapio.cli import app


def test_serve_is_the_only_application_command():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "serve" in result.stdout
    assert "crawl" not in result.stdout
    assert "ingest [" not in result.stdout
