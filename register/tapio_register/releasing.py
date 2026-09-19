"""Cut and verify dated, immutable editions of the register.

``2026-09-19`` is citable; ``main`` is not. A provenance record's
``register_version`` names a directory under ``releases/``, and the manifest's
checksums are what make "the edition that answer was produced against" a
resolvable claim rather than a description of intent.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from tapio_register import paths, skos
from tapio_register.generated.term_register_model import TermRegister
from tapio_register.loading import read_source
from tapio_register.validation import summarize

MANIFEST_NAME = "manifest.json"
SOURCE_NAME = "register.yaml"
JSONLD_NAME = "register.jsonld"
TURTLE_NAME = "register.ttl"


class ReleaseExistsError(Exception):
    """Raised when a release directory is already present.

    Editions are immutable. Re-cutting one would silently invalidate every
    provenance record that names it.
    """


@dataclass(frozen=True)
class ReleaseResult:
    """Where an edition landed and what it contains."""

    directory: Path
    files: list[Path]
    summary: dict[str, object]


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_release(
    register: TermRegister,
    source_path: Path | None = None,
    releases_dir: Path | None = None,
    *,
    overwrite: bool = False,
) -> ReleaseResult:
    """Write the edition named by ``register.register_version``."""
    root = releases_dir or paths.RELEASES_DIR
    directory = root / register.register_version.isoformat()
    if directory.exists() and not overwrite:
        message = (
            f"{directory} already exists. Editions are immutable: bump register_version "
            f"in the source, or pass --overwrite to redo an edition that has not been published."
        )
        raise ReleaseExistsError(message)
    directory.mkdir(parents=True, exist_ok=True)

    # The source snapshot travels with the edition so a reader never has to
    # reconstruct it from repository history.
    source = read_source(source_path)
    (directory / SOURCE_NAME).write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    graph = skos.to_graph(register)
    for name, rdf_format in ((TURTLE_NAME, "turtle"), (JSONLD_NAME, "json-ld")):
        serialized = graph.serialize(format=rdf_format, auto_compact=True)
        if not serialized.endswith("\n"):
            serialized += "\n"
        (directory / name).write_text(serialized, encoding="utf-8")

    summary = summarize(register)
    files = sorted(p for p in directory.iterdir() if p.name != MANIFEST_NAME)
    manifest = {
        "register_version": register.register_version.isoformat(),
        "title": register.title,
        "license": register.license,
        "coverage_caveat": register.coverage_caveat,
        "summary": summary,
        "files": {path.name: _digest(path) for path in files},
    }
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ReleaseResult(directory, [*files, directory / MANIFEST_NAME], summary)


def released_versions(releases_dir: Path | None = None) -> list[str]:
    """Return every released edition, oldest first."""
    root = releases_dir or paths.RELEASES_DIR
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / MANIFEST_NAME).exists())


def verify_releases(releases_dir: Path | None = None) -> list[str]:
    """Return the ways the released editions differ from their manifests.

    Run in CI: an edition whose bytes have changed since it was cut is no
    longer the thing a provenance record pointed at.
    """
    root = releases_dir or paths.RELEASES_DIR
    problems: list[str] = []
    for version in released_versions(root):
        directory = root / version
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        recorded = manifest.get("files", {})
        if manifest.get("register_version") != version:
            problems.append(f"{version}: manifest names version {manifest.get('register_version')}")
        for name, digest in recorded.items():
            path = directory / name
            if not path.exists():
                problems.append(f"{version}/{name}: missing")
            elif _digest(path) != digest:
                problems.append(f"{version}/{name}: checksum does not match the manifest")
        problems.extend(
            f"{version}/{path.name}: present but not in the manifest"
            for path in sorted(directory.iterdir())
            if path.name != MANIFEST_NAME and path.name not in recorded
        )
    return problems


def verify_source_edition(source_path: Path | None = None, releases_dir: Path | None = None) -> list[str]:
    """Check the source still matches the edition its ``register_version`` names.

    Editing the register without bumping its version would otherwise leave the
    released edition quietly out of date, which is the one way a dated release
    can start lying.
    """
    source = read_source(source_path)
    version = str(source.get("register_version"))
    root = releases_dir or paths.RELEASES_DIR
    released = root / version / SOURCE_NAME
    if not released.exists():
        return [f"the source names version {version}, which has not been released"]
    if yaml.safe_load(released.read_text(encoding="utf-8")) != source:
        message = (
            f"the source differs from the {version} edition. Editions are immutable: "
            f"bump register_version and release again."
        )
        return [message]
    return []


def diff_releases(earlier: str, later: str, releases_dir: Path | None = None) -> dict[str, list[str]]:
    """Compare two editions: what was added, what lapsed, what was re-scoped.

    This is the operation the register exists to make cheap - "how many of the
    steps in that process changed between these dates, and which ones".
    """
    root = releases_dir or paths.RELEASES_DIR

    def load(version: str) -> dict[str, dict]:
        source = yaml.safe_load((root / version / SOURCE_NAME).read_text(encoding="utf-8"))
        return {concept["id"]: concept for concept in source["concepts"]}

    before, after = load(earlier), load(later)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    lapsed = sorted(
        concept_id
        for concept_id in set(before) & set(after)
        if before[concept_id].get("valid_until") is None and after[concept_id].get("valid_until") is not None
    )
    changed = sorted(
        concept_id
        for concept_id in set(before) & set(after)
        if before[concept_id] != after[concept_id] and concept_id not in lapsed
    )
    return {"added": added, "lapsed": lapsed, "changed": changed, "withdrawn": removed}


def latest_version(releases_dir: Path | None = None) -> str | None:
    """Return the most recent released edition, if there is one."""
    versions = released_versions(releases_dir)
    return versions[-1] if versions else None


def today() -> date:
    """Today's date, as the default edition name."""
    return date.today()  # noqa: DTZ011 - an edition is named by calendar day, not by instant
