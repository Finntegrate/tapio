"""Editions are immutable, and the manifest is what makes that checkable."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from tapio_register import paths, releasing, validation
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


def test_rebuilding_the_same_edition_is_idempotent(tmp_path, source, register):
    """The payload is not kept in the repository, so rebuilding it is ordinary."""
    first = release(tmp_path, source, register)
    digests = json.loads((first.directory / "manifest.json").read_text(encoding="utf-8"))
    again = release(tmp_path, source, register)
    assert json.loads((again.directory / "manifest.json").read_text(encoding="utf-8")) == digests


def test_releasing_different_content_into_an_existing_edition_is_refused(tmp_path, source, register_dict):
    """This is what immutability means once the payload is rebuilt rather than stored."""
    release(tmp_path, source, TermRegister.model_validate(register_dict))
    register_dict["concepts"][0]["notation"] = "changed without bumping the version"
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    with pytest.raises(releasing.ReleaseExistsError, match="immutable"):
        release(tmp_path, source, TermRegister.model_validate(register_dict))


def test_a_release_whose_source_is_a_different_register_is_refused(tmp_path, source, register, register_dict):
    """Every artifact in an edition has to describe the same register."""
    other = {**register_dict, "title": "A different register"}
    source.write_text(yaml.safe_dump(other, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="not the same register"):
        release(tmp_path, source, register)


def test_overwrite_is_available_for_an_unpublished_edition(tmp_path, source, register):
    release(tmp_path, source, register)
    result = release(tmp_path, source, register, overwrite=True)
    assert result.directory.exists()
    assert result.replaced == []


def test_an_overwrite_reports_what_it_changed(tmp_path, source, register, register_dict):
    """The one way a released edition changes identity, so it does not do so quietly."""
    release(tmp_path, source, register)
    register_dict["title"] = "Renamed edition"
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    result = release(tmp_path, source, TermRegister.model_validate(register_dict), overwrite=True)
    assert "title" in result.replaced
    assert "register.yaml" in result.replaced


def test_verify_passes_on_a_fresh_release(tmp_path, source, register):
    release(tmp_path, source, register)
    assert releasing.verify_releases(tmp_path / "releases") == []


def test_verify_catches_an_edited_edition(tmp_path, source, register):
    result = release(tmp_path, source, register)
    (result.directory / "register.ttl").write_text("# tampered\n", encoding="utf-8")
    problems = releasing.verify_releases(tmp_path / "releases")
    assert any("checksum does not match" in problem for problem in problems)


def test_verify_ignores_a_payload_file_that_was_not_built(tmp_path, source, register):
    """The repository keeps manifests; the files they describe are built on demand."""
    result = release(tmp_path, source, register)
    (result.directory / "register.jsonld").unlink()
    assert releasing.verify_releases(tmp_path / "releases") == []


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


def test_today_is_the_current_calendar_day():
    # Through an aware datetime rather than date.today(), which the linter
    # rejects; astimezone() brings it back to the same local calendar day.
    assert releasing.today() == datetime.now(UTC).astimezone().date()


def test_current_edition_rebuilds_and_matches_right_after_a_release(tmp_path, source, register):
    release(tmp_path, source, register)
    assert releasing.verify_current_edition(source, tmp_path / "releases") == []


def test_current_edition_check_passes_without_the_payload_on_disk(tmp_path, source, register):
    """The point of manifest-only releases: the payload is rebuilt, not stored."""
    result = release(tmp_path, source, register)
    for path in result.directory.iterdir():
        if path.name != "manifest.json":
            path.unlink()
    assert releasing.verify_current_edition(source, tmp_path / "releases") == []


def test_current_edition_check_catches_an_unreleased_edit(tmp_path, source, register, register_dict):
    release(tmp_path, source, register)
    register_dict["concepts"][0]["notation"] = "edited after release"
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    problems = releasing.verify_current_edition(source, tmp_path / "releases")
    assert any("bump register_version" in problem for problem in problems)


def test_current_edition_check_catches_a_version_with_no_manifest(tmp_path, source, register_dict):
    register_dict["register_version"] = "2027-01-01"
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    problems = releasing.verify_current_edition(source, tmp_path / "releases")
    assert any("has no manifest" in problem for problem in problems)


def test_current_edition_check_catches_a_tampered_coverage_caveat(tmp_path, source, register):
    """The caveat is a claim the edition makes about itself, so digests alone are not enough."""
    result = release(tmp_path, source, register)
    manifest_path = result.directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage_caveat"] = "This register is complete and authoritative."
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    problems = releasing.verify_current_edition(source, tmp_path / "releases")
    assert any("coverage_caveat" in problem for problem in problems)


def test_current_edition_check_catches_a_hand_edited_manifest(tmp_path, source, register):
    result = release(tmp_path, source, register)
    manifest_path = result.directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["register.ttl"] = "sha256:" + "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    problems = releasing.verify_current_edition(source, tmp_path / "releases")
    assert any("does not match the digest recorded" in problem for problem in problems)


def test_an_edition_whose_payload_is_not_built_says_how_to_rebuild_it():
    """Only manifests are committed; the payload is rebuilt rather than recovered."""
    version = releasing.latest_version()
    built = paths.release_dir(version) / releasing.SOURCE_NAME
    set_aside = built.with_suffix(".yaml.set-aside") if built.exists() else None
    if set_aside is not None:
        built.rename(set_aside)
    try:
        with pytest.raises(FileNotFoundError, match="tapio-register release"):
            releasing.edition_source(version)
    finally:
        if set_aside is not None:
            set_aside.rename(built)


def test_an_unknown_edition_says_how_to_build_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="tapio-register release"):
        releasing.edition_source("2099-01-01", tmp_path / "releases")


def test_an_edition_whose_published_skos_is_invalid_is_refused(tmp_path, source, register, monkeypatch):
    """Checked where the artifact is written, not only where it is validated."""
    monkeypatch.setattr(
        releasing,
        "check_publication",
        lambda _register: [validation.Issue(None, "a concept has no skos:prefLabel in sv")],
    )
    with pytest.raises(releasing.InvalidPublicationError, match="not valid"):
        release(tmp_path, source, register)
    assert not (tmp_path / "releases" / "2026-09-19").exists()


def test_a_concept_dropped_since_the_previous_edition_is_refused(tmp_path, source, register, register_dict):
    """ADR 0007's never-delete rule, across editions rather than within one."""
    release(tmp_path, source, register)

    later = {**register_dict, "register_version": "2026-12-01"}
    later["concepts"] = [concept for concept in register_dict["concepts"] if concept["id"] != "org:migri"]
    for concept in later["concepts"]:
        concept.pop("handled_by", None)
    source.write_text(yaml.safe_dump(later, allow_unicode=True), encoding="utf-8")

    dropped = releasing.check_continuity(TermRegister.model_validate(later), tmp_path / "releases")
    assert any("org:migri" in problem and "Never delete, always supersede" in problem for problem in dropped)
    with pytest.raises(releasing.ContinuityError, match="drops concepts"):
        release(tmp_path, source, TermRegister.model_validate(later))


def test_a_concept_that_lapses_rather_than_vanishing_is_accepted(tmp_path, source, register, register_dict):
    release(tmp_path, source, register)

    later = {**register_dict, "register_version": "2026-12-01"}
    later["concepts"] = [dict(concept) for concept in register_dict["concepts"]]
    later["concepts"][1] = {**later["concepts"][1], "valid_until": "2026-11-30", "change_note": "Withdrawn."}
    source.write_text(yaml.safe_dump(later, allow_unicode=True), encoding="utf-8")

    assert releasing.check_continuity(TermRegister.model_validate(later), tmp_path / "releases") == []


def test_the_first_edition_has_nothing_to_be_continuous_with(tmp_path, register):
    assert releasing.check_continuity(register, tmp_path / "releases") == []


def test_a_register_failing_its_own_integrity_rules_is_refused(tmp_path, register_dict):
    """The guard is at the boundary that writes, not only in the command that calls it."""
    register_dict["concepts"][0]["related"] = ["permit:does-not-exist"]
    source = tmp_path / "register.yaml"
    source.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    register = TermRegister.model_validate(register_dict)
    with pytest.raises(releasing.InvalidRegisterError, match="not in the register"):
        release(tmp_path, source, register)
    assert not (tmp_path / "releases" / "2026-09-19").exists()


def test_every_refusal_shares_one_base_so_a_caller_can_catch_them_together():
    for error in (
        releasing.ReleaseExistsError,
        releasing.ContinuityError,
        releasing.InvalidPublicationError,
        releasing.InvalidRegisterError,
    ):
        assert issubclass(error, releasing.ReleaseRefusedError)
