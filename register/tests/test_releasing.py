"""Editions are immutable, and the manifest is what makes that checkable."""

import json
from pathlib import Path

import pytest
import yaml

from tapio_register import releasing
from tapio_register.generated.term_register_model import TermRegister


@pytest.fixture
def source(tmp_path: Path, register_dict: dict) -> Path:
    path = tmp_path / "register.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    return path


def release(tmp_path: Path, source: Path, register: TermRegister, **kw) -> releasing.ReleaseResult:
    return releasing.write_release(register, source_path=source, releases_dir=tmp_path / "releases", **kw)


def test_release_writes_every_artifact(tmp_path, source, register):
    result = release(tmp_path, source, register)
    assert {path.name for path in result.files} == {
        "register.yaml",
        "register.ttl",
        "register.jsonld",
        "manifest.json",
    }
    assert result.directory.name == "2026-09-19"


def test_manifest_records_the_summary_and_the_caveat(tmp_path, source, register):
    result = release(tmp_path, source, register)
    manifest = json.loads((result.directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["concept_count"] == 3
    assert "not ground truth" in manifest["coverage_caveat"]
    assert all(digest.startswith("sha256:") for digest in manifest["files"].values())


def test_releasing_over_an_existing_edition_is_refused(tmp_path, source, register):
    release(tmp_path, source, register)
    with pytest.raises(releasing.ReleaseExistsError, match="immutable"):
        release(tmp_path, source, register)


def test_overwrite_is_available_for_an_unpublished_edition(tmp_path, source, register):
    release(tmp_path, source, register)
    assert release(tmp_path, source, register, overwrite=True).directory.exists()


def test_verify_passes_on_a_fresh_release(tmp_path, source, register):
    release(tmp_path, source, register)
    assert releasing.verify_releases(tmp_path / "releases") == []


def test_verify_catches_an_edited_edition(tmp_path, source, register):
    result = release(tmp_path, source, register)
    (result.directory / "register.ttl").write_text("# tampered\n", encoding="utf-8")
    problems = releasing.verify_releases(tmp_path / "releases")
    assert any("checksum does not match" in problem for problem in problems)


def test_verify_catches_a_missing_file(tmp_path, source, register):
    result = release(tmp_path, source, register)
    (result.directory / "register.jsonld").unlink()
    assert any("missing" in problem for problem in releasing.verify_releases(tmp_path / "releases"))


def test_verify_catches_a_file_the_manifest_does_not_know_about(tmp_path, source, register):
    result = release(tmp_path, source, register)
    (result.directory / "extra.ttl").write_text("# smuggled in\n", encoding="utf-8")
    problems = releasing.verify_releases(tmp_path / "releases")
    assert any("not in the manifest" in problem for problem in problems)


def test_released_versions_and_latest(tmp_path, source, register, register_dict):
    release(tmp_path, source, register)
    register_dict["register_version"] = "2026-12-01"
    later = TermRegister.model_validate(register_dict)
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    release(tmp_path, source, later)
    assert releasing.released_versions(tmp_path / "releases") == ["2026-09-19", "2026-12-01"]
    assert releasing.latest_version(tmp_path / "releases") == "2026-12-01"


def test_latest_version_of_nothing_is_none(tmp_path):
    assert releasing.latest_version(tmp_path / "nothing") is None
    assert releasing.released_versions(tmp_path / "nothing") == []


def test_diff_reports_additions_lapses_and_edits(tmp_path, source, register, register_dict):
    release(tmp_path, source, register)

    later = {**register_dict, "register_version": "2026-12-01"}
    later["concepts"] = [dict(concept) for concept in register_dict["concepts"]]
    later["concepts"][1] = {
        **later["concepts"][1],
        "valid_until": "2026-10-01",
        "superseded_by": ["permit:first-residence-permit"],
    }
    later["concepts"][2] = {**later["concepts"][2], "notation": "changed"}
    later["concepts"].append(
        {
            **register_dict["concepts"][0],
            "id": "permit:brand-new",
            "pref_label": {"en": "brand new", "fi": "aivan uusi", "sv": "helt ny"},
        },
    )
    source.write_text(yaml.safe_dump(later, allow_unicode=True), encoding="utf-8")
    release(tmp_path, source, TermRegister.model_validate(later))

    diff = releasing.diff_releases("2026-09-19", "2026-12-01", tmp_path / "releases")
    assert diff["added"] == ["permit:brand-new"]
    assert diff["lapsed"] == ["permit:residence-permit"]
    assert diff["changed"] == ["org:migri"]
    assert diff["withdrawn"] == []


def test_today_is_a_calendar_day(tmp_path):
    assert releasing.today().isoformat() == releasing.today().isoformat()


def test_source_edition_check_passes_right_after_a_release(tmp_path, source, register):
    release(tmp_path, source, register)
    assert releasing.verify_source_edition(source, tmp_path / "releases") == []


def test_source_edition_check_catches_an_unreleased_edit(tmp_path, source, register, register_dict):
    release(tmp_path, source, register)
    register_dict["concepts"][0]["notation"] = "edited after release"
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    problems = releasing.verify_source_edition(source, tmp_path / "releases")
    assert any("bump register_version" in problem for problem in problems)


def test_source_edition_check_catches_a_version_with_no_release(tmp_path, source, register_dict):
    register_dict["register_version"] = "2027-01-01"
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    problems = releasing.verify_source_edition(source, tmp_path / "releases")
    assert any("has not been released" in problem for problem in problems)
