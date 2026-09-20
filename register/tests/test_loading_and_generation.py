"""Loading the source, and keeping the generated artifacts honest."""

import subprocess
import sys
from enum import StrEnum
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from tapio_register import generation, loading, paths


def test_expand_turns_register_curies_into_iris():
    assert loading.expand("org:migri") == "https://tapio.finntegrate.org/register/organization/migri"
    assert loading.expand("permit:visa") == "https://tapio.finntegrate.org/register/permit/visa"


def test_expand_leaves_external_and_unknown_identifiers_alone():
    assert loading.expand("http://www.yso.fi/onto/yso/p6463") == "http://www.yso.fi/onto/yso/p6463"
    assert loading.expand("mystery:thing") == "mystery:thing"


def test_enum_value_handles_both_shapes():
    class Kind(StrEnum):
        permit = "permit"

    assert loading.enum_value(Kind.permit) == "permit"
    assert loading.enum_value("permit") == "permit"


def test_concepts_are_indexed_by_iri(register):
    index = loading.concepts_by_id(register)
    assert index["org:migri"].pref_label.en == "org:migri"


def test_every_kind_has_a_prefix_and_a_namespace():
    assert set(loading.KIND_PREFIXES.values()) == set(loading.PREFIX_NAMESPACES)


def test_loading_a_malformed_source_fails_loudly(tmp_path: Path, register_dict):
    del register_dict["concepts"][0]["pref_label"]["fi"]
    path = tmp_path / "register.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValidationError):
        loading.load_register(path)


def test_a_source_that_is_not_a_mapping_is_rejected(tmp_path: Path):
    path = tmp_path / "register.yaml"
    path.write_text("- not\n- a mapping\n", encoding="utf-8")
    with pytest.raises(TypeError, match="does not contain a register mapping"):
        loading.read_source(path)


def test_checked_in_artifacts_match_the_schema():
    """CI's guard: a schema change cannot land without its generated artifacts."""
    assert generation.check_generated_is_current() == []


def test_render_produces_both_artifacts():
    rendered = {artifact.path.name: artifact.content for artifact in generation.render_artifacts()}
    assert set(rendered) == {"term_register_model.py", "term_register.schema.json"}
    assert "class Concept" in rendered["term_register_model.py"]
    assert "Do not edit by hand" in rendered["term_register_model.py"]


def test_a_missing_artifact_is_reported_as_stale(tmp_path, monkeypatch):
    artifacts = generation.render_artifacts()
    monkeypatch.setattr(
        generation,
        "render_artifacts",
        lambda *_, **__: [generation.GeneratedArtifact(tmp_path / a.path.name, a.content) for a in artifacts],
    )
    assert len(generation.check_generated_is_current()) == len(artifacts)


def test_generate_writes_every_artifact(tmp_path, monkeypatch):
    artifacts = generation.render_artifacts()
    monkeypatch.setattr(generation.paths, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(
        generation,
        "render_artifacts",
        lambda *_, **__: [generation.GeneratedArtifact(tmp_path / a.path.name, a.content) for a in artifacts],
    )
    written = generation.generate()
    assert {path.name for path in written} == {a.path.name for a in artifacts}
    assert (tmp_path / "__init__.py").exists()
    assert all(path.read_text(encoding="utf-8") for path in written)


def test_reading_the_register_pulls_in_no_authoring_dependencies():
    """A consumer ships the data and reads it; it does not ship the toolchain.

    LinkML, rdflib, jsonschema, typer and httpx are all authoring-time. One
    convenience import in `loading.py` would quietly drag them into anything
    that only wanted to read the register — an API image, a notebook, a script
    — and nothing else would notice.
    """
    probe = (
        "import sys, tapio_register.loading as loading, tapio_register.history as history;"
        "history.in_force_on(loading.load_register(), __import__('datetime').date.today());"
        "print(','.join(m for m in ('linkml','linkml_runtime','rdflib','pyshacl','typer','httpx','jsonschema')"
        " if m in sys.modules))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=paths.SERVICE_DIR,
    )
    assert result.stdout.strip() == "", f"runtime import now pulls in: {result.stdout.strip()}"
