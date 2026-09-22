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
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from tapio_register import paths, skos
from tapio_register.generated.term_register_model import TermRegister
from tapio_register.loading import read_source
from tapio_register.validation import check_integrity, check_publication, summarize

MANIFEST_NAME = "manifest.json"
SOURCE_NAME = "register.yaml"
JSONLD_NAME = "register.jsonld"
TURTLE_NAME = "register.ttl"


class ReleaseRefusedError(Exception):
    """Base for every reason an edition must not be written.

    Each of these is checked in :func:`write_release` rather than in the command
    that calls it, so the guard holds for any caller. A check that lives at one
    call site protects that call site, not the artifact.
    """


class ReleaseExistsError(ReleaseRefusedError):
    """Raised when a release directory is already present.

    Editions are immutable. Re-cutting one would silently invalidate every
    provenance record that names it.
    """


class ContinuityError(ReleaseRefusedError):
    """Raised when an edition drops a concept an earlier one published.

    ADR 0007's "never delete, always supersede": an entity leaves force, it does
    not stop having existed. Within one edition that is a rule about
    ``valid_until``; across editions it is this.
    """


class InvalidPublicationError(ReleaseRefusedError):
    """Raised when an edition's published SKOS would not be valid."""


class InvalidRegisterError(ReleaseRefusedError):
    """Raised when the register does not pass its own cross-concept rules."""


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


def _reasons(headline: str, problems: list[str]) -> str:
    """Render a refusal as a headline and a bulleted list of what is wrong."""
    return headline + "\n  - " + "\n  - ".join(problems)


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

    invalid = [str(issue) for issue in check_integrity(register)]
    if invalid:
        raise InvalidRegisterError(_reasons("this register does not pass its own integrity rules:", invalid))

    problems = [str(issue) for issue in check_publication(register)]
    if problems:
        raise InvalidPublicationError(_reasons("the SKOS this edition would publish is not valid:", problems))

    dropped = check_continuity(register, root)
    if dropped:
        raise ContinuityError(_reasons("this edition drops concepts an earlier one published:", dropped))

    # Built in full before anything in `directory` is touched, so a refused
    # release leaves the edition that is already there exactly as it was, and an
    # interrupted one leaves nothing half-written.
    with tempfile.TemporaryDirectory() as scratch:
        staged = Path(scratch)
        # The source snapshot travels with the edition so a reader never has to
        # reconstruct it from repository history.
        (staged / SOURCE_NAME).write_text(
            yaml.safe_dump(source, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
        graph = skos.to_graph(register)
        for name, rdf_format in ((TURTLE_NAME, "turtle"), (JSONLD_NAME, "json-ld")):
            (staged / name).write_text(skos.serialize(graph, rdf_format), encoding="utf-8")

        summary = summarize(register)
        built = sorted(staged.iterdir())
        manifest: dict[str, Any] = {
            "register_version": register.register_version.isoformat(),
            "title": register.title,
            "license": register.license,
            "coverage_caveat": register.coverage_caveat,
            "summary": summary,
            # Recorded so a later edition can check that nothing was dropped
            # without needing this edition's payload to still be built.
            "concept_ids": sorted(concept.id for concept in register.concepts),
            "files": {path.name: _digest(path) for path in built},
        }
        replaced = _differences(existing, manifest) if existing is not None else []
        if replaced and not overwrite:
            message = (
                f"{directory} already holds a different edition. Editions are immutable: bump "
                f"register_version in the source and release again, or pass --overwrite to redo an "
                f"edition that has not been published."
            )
            raise ReleaseExistsError(message)

        directory.mkdir(parents=True, exist_ok=True)
        files = [shutil.copy2(path, directory / path.name) for path in built]

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ReleaseResult(directory, [*(Path(f) for f in files), manifest_path], summary, manifest, replaced)


def _differences(existing: dict[str, Any], rebuilt: dict[str, Any]) -> list[str]:
    """Name what changed between two manifests, for a caller about to overwrite one."""
    fields = [
        field
        for field in ("register_version", "title", "license", "coverage_caveat", "summary", "concept_ids")
        if existing.get(field) != rebuilt.get(field)
    ]
    existing_files, rebuilt_files = existing.get("files", {}), rebuilt.get("files", {})
    return sorted(fields) + sorted(
        name for name in set(existing_files) | set(rebuilt_files) if existing_files.get(name) != rebuilt_files.get(name)
    )


def check_continuity(register: TermRegister, releases_dir: Path | None = None) -> list[str]:
    """Report concepts an earlier edition published that this one drops.

    Removal is a lossy edit, and the one kind of damage a dated register cannot
    repair after the fact: a consumer holding a provenance record that names an
    older edition has no way to resolve an identifier that simply vanished. A
    concept that no longer applies lapses with a ``valid_until``; it does not
    leave the register.
    """
    root = releases_dir or paths.RELEASES_DIR
    version = register.register_version.isoformat()
    earlier = [released for released in released_versions(root) if released < version]
    if not earlier:
        return []
    previous = earlier[-1]
    recorded = json.loads((root / previous / MANIFEST_NAME).read_text(encoding="utf-8")).get("concept_ids")
    if recorded is None:
        # An edition cut before manifests recorded their concept ids. Say so
        # rather than reporting a clean check that did not happen.
        return [f"the {previous} manifest records no concept ids, so continuity with it cannot be checked"]
    published = set(recorded)
    current = {concept.id for concept in register.concepts}
    return [
        f"{concept_id}: published in {previous} and absent here. Never delete, always supersede: "
        f"give it a valid_until and a superseded_by instead."
        for concept_id in sorted(published - current)
    ]


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
    # The concept ids are what the next edition's continuity check reads, so an
    # edited list would otherwise let a dropped concept through unnoticed.
    problems.extend(_concept_id_problems(recorded.get("concept_ids"), rebuilt["concept_ids"], version))
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


def _concept_id_problems(recorded: list[str] | None, rebuilt: list[str], version: str) -> list[str]:
    """Name the concept ids a manifest and its source disagree about."""
    if recorded is None:
        return [f"manifest concept_ids: the {version} manifest records none, so continuity cannot be checked"]
    missing = sorted(set(rebuilt) - set(recorded))
    extra = sorted(set(recorded) - set(rebuilt))
    problems = [f"manifest concept_ids: {c} is in the source and not in the manifest" for c in missing]
    problems += [f"manifest concept_ids: {c} is in the manifest and not in the source" for c in extra]
    if not problems and recorded != rebuilt:
        problems.append("manifest concept_ids: the same ids, recorded in a different order")
    return problems


def edition_source(version: str, releases_dir: Path | None = None) -> dict:
    """Return the register source an edition was cut from, if its payload is built.

    Only manifests are committed, so an older edition's payload is usually
    absent until someone rebuilds it. The cross-edition check does not depend on
    this: it reads the concept ids the manifest records.
    """
    root = releases_dir or paths.RELEASES_DIR
    snapshot = root / version / SOURCE_NAME
    if not snapshot.exists():
        message = (
            f"{snapshot} is not built. Check out the commit that wrote the {version} manifest "
            f"and run `tapio-register release`."
        )
        raise FileNotFoundError(message)
    return yaml.safe_load(snapshot.read_text(encoding="utf-8"))


def diff_releases(earlier: str, later: str, releases_dir: Path | None = None) -> dict[str, Any]:
    """Compare two editions: what was added, what lapsed, what was re-scoped.

    This is the operation the register exists to make cheap - "how many of the
    steps in that process changed between these dates, and which ones".

    A full comparison needs both editions' payloads, and a clean checkout holds
    only their manifests. Rather than fail there, this falls back to the concept
    ids the manifests record, which answers what came and went but not what
    changed within a concept. ``compared`` says which of the two it did.
    """

    def load(version: str) -> dict[str, dict]:
        source = edition_source(version, releases_dir)
        return {concept["id"]: concept for concept in source["concepts"]}

    try:
        before, after = load(earlier), load(later)
    except FileNotFoundError:
        return _manifest_diff(earlier, later, releases_dir)
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
    return {"added": added, "lapsed": lapsed, "changed": changed, "withdrawn": removed, "compared": "sources"}


def _manifest_diff(earlier: str, later: str, releases_dir: Path | None = None) -> dict[str, Any]:
    """Compare two editions by the concept ids their manifests record."""
    root = releases_dir or paths.RELEASES_DIR

    def ids(version: str) -> set[str]:
        manifest_path = root / version / MANIFEST_NAME
        if not manifest_path.exists():
            message = f"there is no {version} edition in {root.name}/"
            raise FileNotFoundError(message)
        recorded = json.loads(manifest_path.read_text(encoding="utf-8")).get("concept_ids")
        if recorded is None:
            message = (
                f"the {version} manifest records no concept ids, and its payload is not built. "
                f"Check out the commit that wrote it and run `tapio-register release` to compare."
            )
            raise FileNotFoundError(message)
        return set(recorded)

    before, after = ids(earlier), ids(later)
    return {
        "added": sorted(after - before),
        "withdrawn": sorted(before - after),
        "compared": (
            "manifest concept ids only - neither edition's payload is built, so what lapsed or "
            "changed within a concept cannot be seen. Run `tapio-register release` at each "
            "edition's commit for the full comparison."
        ),
    }


def latest_version(releases_dir: Path | None = None) -> str | None:
    """Return the most recent released edition, if there is one."""
    versions = released_versions(releases_dir)
    return versions[-1] if versions else None


def today() -> date:
    """Today's date, as the default edition name."""
    # An edition is named by calendar day, not by instant.
    return date.today()  # noqa: DTZ011
