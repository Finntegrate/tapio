"""Command line for validating, generating, releasing, and seeding the register."""

import json
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
import yaml

from tapio_register import generation, loading, paths, releasing, skos, validation
from tapio_register.seeding import finto

app = typer.Typer(help="Tapio's versioned term register.", no_args_is_help=True)


def _display(path: Path) -> str:
    """Show a path relative to the service directory when it is inside it."""
    try:
        return str(path.relative_to(paths.SERVICE_DIR))
    except ValueError:
        return str(path)


def _unused_candidate_path(vocabulary: str, harvested_on: str) -> Path:
    """Pick a candidate filename that is not already taken.

    A second harvest on the same day would otherwise overwrite the first, and
    what it would discard is a queue of candidates nobody has reviewed yet.
    """
    base = paths.CANDIDATES_DIR / f"finto-{vocabulary}-{harvested_on}.yaml"
    candidate, index = base, 1
    while candidate.exists():
        candidate = base.with_name(f"{base.stem}-{index}{base.suffix}")
        index += 1
    return candidate


def _echo_issues(label: str, issues: list[str]) -> None:
    typer.echo(f"{label}: {len(issues)}")
    for issue in issues:
        typer.echo(f"  - {issue}")


@app.command()
def validate(
    source: Annotated[Path | None, typer.Option("--source", help="Register source to validate.")] = None,
    skip_schema: Annotated[
        bool,
        typer.Option("--skip-schema", help="Skip the JSON Schema pass."),
    ] = False,
) -> None:
    """Check the register against the schema, the integrity rules, and the published SKOS."""
    register = loading.load_register(source)
    schema_issues = [] if skip_schema else [str(issue) for issue in validation.check_schema(source)]
    integrity_issues = [str(issue) for issue in validation.check_integrity(register)]
    publication_issues = [str(issue) for issue in validation.check_publication(register)]
    continuity_issues = releasing.check_continuity(register)
    if not skip_schema:
        _echo_issues("Schema violations", schema_issues)
    _echo_issues("Integrity violations", integrity_issues)
    _echo_issues("Publication violations", publication_issues)
    _echo_issues("Continuity violations", continuity_issues)
    if schema_issues or integrity_issues or publication_issues or continuity_issues:
        raise typer.Exit(code=1)
    summary = validation.summarize(register)
    typer.echo(f"OK: {summary['concept_count']} concepts, version {summary['register_version']}")


@app.command()
def summary(
    source: Annotated[Path | None, typer.Option("--source", help="Register source to describe.")] = None,
) -> None:
    """Print what the register covers."""
    typer.echo(json.dumps(validation.summarize(loading.load_register(source)), indent=2, ensure_ascii=False))


@app.command()
def generate(
    check: Annotated[
        bool,
        typer.Option("--check", help="Report whether the checked-in artifacts are current instead of rewriting them."),
    ] = False,
) -> None:
    """Derive the Pydantic classes and JSON Schema from the LinkML schema."""
    if check:
        stale = generation.check_generated_is_current()
        if stale:
            for path in stale:
                typer.echo(f"stale: {_display(path)}")
            typer.echo("Run `tapio-register generate` and commit the result.")
            raise typer.Exit(code=1)
        typer.echo("Generated artifacts are current.")
        return
    for path in generation.generate():
        typer.echo(f"wrote {_display(path)}")


@app.command()
def release(
    source: Annotated[Path | None, typer.Option("--source", help="Register source to release.")] = None,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help=(
                "Rewrite an edition into different content. Only for one that has not been "
                "published: rebuilding an unchanged edition needs no flag."
            ),
        ),
    ] = False,
) -> None:
    """Cut the dated edition named by the source's ``register_version``."""
    register = loading.load_register(source)
    try:
        # Every reason to refuse lives in `write_release`, so this command and a
        # programmatic caller are held to the same rules.
        result = releasing.write_release(register, source_path=source, overwrite=overwrite)
    except releasing.ReleaseRefusedError as error:
        typer.echo(f"Refusing to release: {error}")
        raise typer.Exit(code=1) from error
    if result.replaced:
        # An overwrite is the one way a released edition can change identity, so
        # it says what it changed rather than doing it quietly.
        typer.echo(f"overwrote edition {register.register_version}, changing: {', '.join(result.replaced)}")
    for path in result.files:
        typer.echo(f"wrote {_display(path)}")


@app.command("verify-releases")
def verify_releases(
    source: Annotated[Path | None, typer.Option("--source", help="Register source to check against.")] = None,
) -> None:
    """Check the released editions, and rebuild the one the source names."""
    problems = releasing.verify_releases() + releasing.verify_current_edition(source)
    if problems:
        _echo_issues("Release problems", problems)
        raise typer.Exit(code=1)
    versions = releasing.released_versions()
    typer.echo(f"OK: {len(versions)} edition(s) verified: {', '.join(versions) or 'none'}")


@app.command()
def diff(
    earlier: Annotated[str, typer.Argument(help="The older edition, e.g. 2026-09-19.")],
    later: Annotated[str, typer.Argument(help="The newer edition.")],
) -> None:
    """Show what changed between two editions."""
    typer.echo(json.dumps(releasing.diff_releases(earlier, later), indent=2, ensure_ascii=False))


@app.command("in-force")
def in_force(
    reference: Annotated[str, typer.Argument(help="A date, e.g. 2024-03-01.")],
    source: Annotated[Path | None, typer.Option("--source", help="Register source to read.")] = None,
) -> None:
    """List the concepts that were in force on a date."""
    register = loading.load_register(source)
    for concept in skos.in_force_on(register, date.fromisoformat(reference)):
        typer.echo(f"{concept.id}\t{concept.pref_label.en}")


@app.command("seed-finto")
def seed_finto(
    queries: Annotated[list[str], typer.Argument(help="Search terms, e.g. oleskelulupa viisumi.")],
    vocabulary: Annotated[str, typer.Option("--vocab", help="Finto vocabulary id, e.g. yso or jupo.")] = "yso",
    language: Annotated[str, typer.Option("--lang", help="Language the search terms are in.")] = "fi",
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the candidate file.")] = None,
) -> None:
    """Harvest candidate concepts from Finto into the review queue.

    Reaches the network, so it is run by hand rather than in CI. Nothing it
    writes is part of the register until a person moves it across.
    """
    candidates = finto.harvest(list(queries), vocabulary=vocabulary, language=language)
    payload = finto.as_candidate_file(candidates, list(queries), vocabulary)
    destination = out or _unused_candidate_path(vocabulary, str(payload["harvested_on"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    typer.echo(f"wrote {len(candidates)} candidate(s) to {destination}")


def main() -> None:
    """Entry point for ``tapio-register``."""
    app()


if __name__ == "__main__":
    main()
