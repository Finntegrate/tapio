"""The CLI is how the register is checked and released, including in CI."""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from tapio_register import paths
from tapio_register.cli import app

runner = CliRunner()


@pytest.fixture
def source(tmp_path: Path, register_dict: dict) -> Path:
    path = tmp_path / "register.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    return path


def test_validate_accepts_the_shipped_register():
    result = runner.invoke(app, ["validate", "--skip-shapes"])
    assert result.exit_code == 0, result.output
    assert "OK:" in result.output


def test_validate_reports_and_fails_on_a_broken_register(tmp_path, register_dict):
    register_dict["concepts"][0]["related"] = ["permit:nope"]
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    result = runner.invoke(app, ["validate", "--skip-shapes", "--source", str(path)])
    assert result.exit_code == 1
    assert "not in the register" in result.output


def test_summary_prints_coverage(source):
    result = runner.invoke(app, ["summary", "--source", str(source)])
    assert result.exit_code == 0
    assert json.loads(result.output)["concept_count"] == 3


def test_generate_check_passes_on_the_checked_in_artifacts():
    result = runner.invoke(app, ["generate", "--check"])
    assert result.exit_code == 0, result.output
    assert "current" in result.output


def test_verify_releases_passes_on_the_shipped_editions():
    result = runner.invoke(app, ["verify-releases"])
    assert result.exit_code == 0, result.output


def test_in_force_lists_concepts_at_a_date(source):
    result = runner.invoke(app, ["in-force", "2026-01-01", "--source", str(source)])
    assert result.exit_code == 0
    assert "permit:first-residence-permit" in result.output


def test_release_refuses_an_invalid_register(tmp_path, register_dict, monkeypatch):
    register_dict["concepts"][0]["handled_by"] = ["permit:residence-permit"]
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(paths, "RELEASES_DIR", tmp_path / "releases")
    result = runner.invoke(app, ["release", "--source", str(path)])
    assert result.exit_code == 1
    assert "Refusing to release" in result.output


def test_release_rebuilds_an_edition_but_refuses_to_change_one(tmp_path, source, register_dict, monkeypatch):
    monkeypatch.setattr(paths, "RELEASES_DIR", tmp_path / "releases")
    first = runner.invoke(app, ["release", "--source", str(source)])
    assert first.exit_code == 0, first.output
    again = runner.invoke(app, ["release", "--source", str(source)])
    assert again.exit_code == 0, again.output

    register_dict["concepts"][0]["notation"] = "changed without bumping the version"
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    changed = runner.invoke(app, ["release", "--source", str(source)])
    assert changed.exit_code == 1
    assert "immutable" in changed.output


def test_diff_compares_two_editions(tmp_path, source, register_dict, monkeypatch):
    monkeypatch.setattr(paths, "RELEASES_DIR", tmp_path / "releases")
    assert runner.invoke(app, ["release", "--source", str(source)]).exit_code == 0
    register_dict["register_version"] = "2026-12-01"
    register_dict["concepts"].append(
        {
            **register_dict["concepts"][0],
            "id": "permit:new-thing",
            "pref_label": {"en": "new thing", "fi": "uusi asia", "sv": "ny sak"},
        },
    )
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    second = runner.invoke(app, ["release", "--source", str(source)])
    assert second.exit_code == 0, second.output
    result = runner.invoke(app, ["diff", "2026-09-19", "2026-12-01"])
    assert result.exit_code == 0
    assert json.loads(result.output)["added"] == ["permit:new-thing"]


def test_seed_finto_writes_a_candidate_file(tmp_path, monkeypatch):
    """The seeding command reaches the network, so the harvest itself is stubbed."""
    from tapio_register.seeding import finto

    monkeypatch.setattr(
        finto,
        "harvest",
        lambda *_, **__: [finto.Candidate(uri="http://www.yso.fi/onto/yso/p1", vocabulary="yso")],
    )
    destination = tmp_path / "candidates.yaml"
    result = runner.invoke(app, ["seed-finto", "oleskelulupa", "--out", str(destination)])
    assert result.exit_code == 0, result.output
    payload = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert payload["queries"] == ["oleskelulupa"]
    assert payload["candidates"][0]["reviewed"] is False


def test_a_second_harvest_on_the_same_day_does_not_overwrite_the_first(tmp_path, monkeypatch):
    """What it would discard is a queue of candidates nobody has reviewed yet."""
    from tapio_register.seeding import finto

    monkeypatch.setattr(paths, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(
        finto,
        "harvest",
        lambda *_, **__: [finto.Candidate(uri="http://www.yso.fi/onto/yso/p1", vocabulary="yso")],
    )
    first = runner.invoke(app, ["seed-finto", "oleskelulupa"])
    second = runner.invoke(app, ["seed-finto", "viisumi"])
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output

    written = sorted(path.name for path in tmp_path.iterdir())
    assert len(written) == 2, written
    queries = [yaml.safe_load((tmp_path / name).read_text(encoding="utf-8"))["queries"] for name in written]
    assert sorted(queries) == [["oleskelulupa"], ["viisumi"]]
