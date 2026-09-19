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
        (directory / name).write_text(skos.serialize(graph, rdf_format), encoding="utf-8")

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
    would otherwise leave the recorded digests describing something that no
    longer exists.
    """
    source = read_source(source_path)
    version = str(source.get("register_version"))
    root = releases_dir or paths.RELEASES_DIR
    manifest_path = root / version / MANIFEST_NAME
    if not manifest_path.exists():
        return [f"the source names version {version}, which has no manifest in {root.name}/"]

    recorded = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {})
    register = TermRegister.model_validate(source)
    with tempfile.TemporaryDirectory() as scratch:
        rebuilt = write_release(register, source_path=source_path, releases_dir=Path(scratch), overwrite=True)
        digests = {path.name: _digest(path) for path in rebuilt.directory.iterdir() if path.name != MANIFEST_NAME}

    problems = [
        f"{name}: the manifest records a file the release no longer produces"
        for name in sorted(set(recorded) - set(digests))
    ]
    problems.extend(
        f"{name}: the release produces a file the manifest does not record"
        for name in sorted(set(digests) - set(recorded))
    )
    problems.extend(
        f"{name}: rebuilt from the source, it does not match the digest recorded for {version}. "
        f"Editions are immutable: bump register_version and release again."
        for name in sorted(set(recorded) & set(digests))
        if recorded[name] != digests[name]
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
