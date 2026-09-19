"""Cut and verify dated, immutable editions of the register.

``2026-09-19`` is citable; ``main`` is not. A provenance record's
``register_version`` names an edition, and the manifest's checksums are what
make "the edition that answer was produced against" a resolvable claim rather
than a description of intent.

Only the manifest is kept in the repository. The payload it describes - the
SKOS serializations and the source snapshot - is built from
``data/register.yaml`` on demand, because committing it would bury a
three-line concept change in a fourteen-thousand-line diff and make the
register harder to maintain than to build. The integrity claim stays in git
either way: the digests are recorded, the serializations are reproducible
(see :func:`tapio_register.skos.serialize`), and
:func:`verify_current_edition` rebuilds the payload and checks it against
them.
"""

import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

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
    summary: dict[str, Any]
    manifest: dict[str, Any]
    #: What ``--overwrite`` changed in an edition that already existed. Empty
    #: for a new edition, and for a rebuild that reproduced what was there.
    replaced: list[str]


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_release(
    register: TermRegister,
    source_path: Path | None = None,
    releases_dir: Path | None = None,
    *,
    overwrite: bool = False,
) -> ReleaseResult:
    """Write the edition named by ``register.register_version``.

    Rebuilding an edition that already exists is ordinary - the payload is not
    kept in the repository - so this is idempotent while the source still
    produces the same bytes. What it refuses is rewriting a manifest into
    something different, because that is how a published edition quietly stops
    being the thing a provenance record named.
    """
    root = releases_dir or paths.RELEASES_DIR
    directory = root / register.register_version.isoformat()
    manifest_path = directory / MANIFEST_NAME
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None

    source = read_source(source_path)
    if TermRegister.model_validate(source) != register:
        message = "the register being released and the source snapshot are not the same register"
        raise ValueError(message)

    directory.mkdir(parents=True, exist_ok=True)
    # The source snapshot travels with the edition so a reader never has to
    # reconstruct it from repository history.
    (directory / SOURCE_NAME).write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    graph = skos.to_graph(register)
    for name, rdf_format in ((TURTLE_NAME, "turtle"), (JSONLD_NAME, "json-ld")):
        (directory / name).write_text(skos.serialize(graph, rdf_format), encoding="utf-8")

    summary = summarize(register)
    files = sorted(path for path in directory.iterdir() if path.name != MANIFEST_NAME)
    manifest: dict[str, Any] = {
        "register_version": register.register_version.isoformat(),
        "title": register.title,
        "license": register.license,
        "coverage_caveat": register.coverage_caveat,
        "summary": summary,
        "files": {path.name: _digest(path) for path in files},
    }
    replaced = _differences(existing, manifest) if existing is not None else []
    if replaced and not overwrite:
        message = (
            f"{directory} already holds a different edition. Editions are immutable: bump "
            f"register_version in the source and release again, or pass --overwrite to redo an "
            f"edition that has not been published."
        )
        raise ReleaseExistsError(message)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ReleaseResult(directory, [*files, manifest_path], summary, manifest, replaced)


def _differences(existing: dict[str, Any], rebuilt: dict[str, Any]) -> list[str]:
    """Name what changed between two manifests, for a caller about to overwrite one."""
    fields = [
        field
        for field in ("register_version", "title", "license", "coverage_caveat", "summary")
        if existing.get(field) != rebuilt.get(field)
    ]
    existing_files, rebuilt_files = existing.get("files", {}), rebuilt.get("files", {})
    return sorted(fields) + sorted(
        name for name in set(existing_files) | set(rebuilt_files) if existing_files.get(name) != rebuilt_files.get(name)
    )


def released_versions(releases_dir: Path | None = None) -> list[str]:
    """Return every released edition, oldest first."""
    root = releases_dir or paths.RELEASES_DIR
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / MANIFEST_NAME).exists())


def verify_releases(releases_dir: Path | None = None) -> list[str]:
    """Check every released edition still matches the manifest it was cut with.

    A payload file is only checked when it is present: the repository keeps the
    manifests, and the files they describe are built on demand or published
    elsewhere. An absent file is therefore not a problem, and a *changed* one
    is.
    """
    root = releases_dir or paths.RELEASES_DIR
    problems: list[str] = []
    for version in released_versions(root):
        directory = root / version
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        recorded = manifest.get("files", {})
        if manifest.get("register_version") != version:
            problems.append(f"{version}: manifest names version {manifest.get('register_version')}")
        problems.extend(
            f"{version}/{name}: checksum does not match the manifest"
            for name, digest in sorted(recorded.items())
            if (directory / name).exists() and _digest(directory / name) != digest
        )
        problems.extend(
            f"{version}/{path.name}: present but not in the manifest"
            for path in sorted(directory.iterdir())
            if path.name != MANIFEST_NAME and path.name not in recorded
        )
    return problems


def verify_current_edition(source_path: Path | None = None, releases_dir: Path | None = None) -> list[str]:
    """Rebuild the edition the source names and check it against the manifest.

    This is the check that keeps a manifest-only release honest. It catches a
    register edited without bumping its version, a manifest edited by hand, and
    a change that makes the serializations stop reproducing - each of which
    would otherwise leave the manifest describing something that no longer
    exists. The published metadata is compared too, not only the digests: the
    coverage caveat is a claim the edition makes about itself, and a tampered
    one would otherwise pass.
    """
    source = read_source(source_path)
    version = str(source.get("register_version"))
    root = releases_dir or paths.RELEASES_DIR
    manifest_path = root / version / MANIFEST_NAME
    if not manifest_path.exists():
        return [f"the source names version {version}, which has no manifest in {root.name}/"]

    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    register = TermRegister.model_validate(source)
    with tempfile.TemporaryDirectory() as scratch:
        rebuilt = write_release(register, source_path=source_path, releases_dir=Path(scratch), overwrite=True).manifest

    problems = [
        f"manifest {field}: recorded value does not match the source"
        for field in ("register_version", "title", "license", "coverage_caveat", "summary")
        if recorded.get(field) != rebuilt[field]
    ]
    recorded_files: dict[str, str] = recorded.get("files", {})
    rebuilt_files: dict[str, str] = rebuilt["files"]
    problems.extend(
        f"{name}: the manifest records a file the release no longer produces"
        for name in sorted(set(recorded_files) - set(rebuilt_files))
    )
    problems.extend(
        f"{name}: the release produces a file the manifest does not record"
        for name in sorted(set(rebuilt_files) - set(recorded_files))
    )
    problems.extend(
        f"{name}: rebuilt from the source, it does not match the digest recorded for {version}. "
        f"Editions are immutable: bump register_version and release again."
        for name in sorted(set(recorded_files) & set(rebuilt_files))
        if recorded_files[name] != rebuilt_files[name]
    )
    return problems


def diff_releases(earlier: str, later: str, releases_dir: Path | None = None) -> dict[str, list[str]]:
    """Compare two editions: what was added, what lapsed, what was re-scoped.

    This is the operation the register exists to make cheap - "how many of the
    steps in that process changed between these dates, and which ones".
    """
    root = releases_dir or paths.RELEASES_DIR

    def load(version: str) -> dict[str, dict]:
        snapshot = root / version / SOURCE_NAME
        if not snapshot.exists():
            message = f"{snapshot} is not built. Run `tapio-register release` for {version} first."
            raise FileNotFoundError(message)
        source = yaml.safe_load(snapshot.read_text(encoding="utf-8"))
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
