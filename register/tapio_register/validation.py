"""Checks the register has to pass before it can be released.

Three layers, cheapest first:

1. the generated Pydantic classes, which enforce the shape of each concept;
2. the generated JSON Schema and SHACL shapes, run through LinkML's validator,
   which is what proves the generated artifacts are usable and not just present;
3. the cross-concept rules below, which are what ADR 0007's "never delete,
   always supersede" and closed-world posture actually amount to in practice.

A rule enforced here is a rule a reviewer does not have to remember.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tapio_register import paths
from tapio_register.generated.term_register_model import Concept, Observation, TermRegister
from tapio_register.loading import KIND_PREFIXES, enum_value, read_source

#: Longest a label can be before it reads as a definition rather than a term.
_LABEL_MAX = 120

#: Two concepts sharing a surface form is the collision the ground node cannot resolve.
_COLLISION = 2

#: Slots whose values must resolve to a concept in this same register.
_REFERENCE_SLOTS = ("superseded_by", "broader", "related", "handled_by")


@dataclass(frozen=True)
class Issue:
    """One problem found in the register, attributed to a concept where possible."""

    concept_id: str | None
    message: str

    def __str__(self) -> str:
        """Render as ``concept: message``, or just the message when unattributed."""
        return f"{self.concept_id}: {self.message}" if self.concept_id else self.message


def normalize_label(label: str) -> str:
    """Fold a surface form the way the harness's ``ground`` node will.

    Case and surrounding whitespace are not meaningful; everything else is left
    alone, because the register carries Finnish and Swedish and stripping
    diacritics would merge terms that differ.
    """
    return " ".join(label.lower().split())


def check_schema(source_path: Path | None = None, schema_path: Path | None = None) -> list[Issue]:
    """Validate the source against the generated JSON Schema and SHACL shapes.

    Running both is what proves the generated artifacts are usable rather than
    merely present: the JSON Schema and the shapes checked here are the
    checked-in copies, the same files a consumer and the harness's own gates G3
    to G5 will load, rather than ones generated for the occasion.
    """
    schema = str(schema_path or paths.SCHEMA_PATH)
    source = read_source(source_path)
    return [*_jsonschema_issues(source), *_shacl_issues(schema, source)]


def _jsonschema_issues(source: dict[str, Any]) -> list[Issue]:
    """Validate against the checked-in JSON Schema, not one generated on the fly.

    Generating it here would only prove the LinkML source is self-consistent.
    Loading the committed artifact is what proves the file consumers actually
    read is the one the register satisfies.
    """
    import jsonschema

    schema = json.loads(paths.JSON_SCHEMA_PATH.read_text(encoding="utf-8"))
    # Dates arrive from YAML as `date` objects, which JSON Schema cannot see; a
    # round trip renders them the way a consumer reading the published JSON would.
    instance = json.loads(json.dumps(source, default=str))
    validator = jsonschema.Draft202012Validator(schema)
    return [
        Issue(None, f"{error.message} in /{'/'.join(str(part) for part in error.absolute_path)}")
        for error in sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    ]


def _shacl_issues(schema: str, source: dict[str, Any]) -> list[Issue]:
    """Validate the register as RDF against the checked-in SHACL shapes.

    LinkML ships a SHACL validation plugin, but it drives pyshacl through an
    API that pyshacl has since changed, so the conversion and the validate call
    are done here instead.
    """
    import pyshacl
    from linkml.generators import PythonGenerator
    from linkml_runtime.dumpers import rdflib_dumper
    from linkml_runtime.utils.schemaview import SchemaView
    from rdflib import Graph

    module = PythonGenerator(schema).compile_module()
    try:
        instance = module.TermRegister(**source)
    except (ValueError, TypeError) as error:
        return [Issue(None, f"could not be converted to RDF for shape validation: {error}")]

    data_graph = rdflib_dumper.as_rdf_graph(instance, schemaview=SchemaView(schema))
    shapes = Graph().parse(paths.SHACL_PATH, format="turtle")
    conforms, _, report = pyshacl.validate(data_graph=data_graph, shacl_graph=shapes, inference="rdfs")
    if conforms:
        return []
    # pyshacl's third return value is its human-readable report; the "Message:"
    # lines are the individual constraint violations.
    return [Issue(None, line.strip()) for line in str(report).splitlines() if line.strip().startswith("Message:")]


def _check_identifiers(concepts: list[Concept]) -> list[Issue]:
    """Report duplicate ids, and ids whose prefix does not match the concept's kind."""
    issues: list[Issue] = []
    seen: set[str] = set()
    for concept in concepts:
        if concept.id in seen:
            issues.append(Issue(concept.id, "duplicate concept id"))
        seen.add(concept.id)
        prefix, separator, local = concept.id.partition(":")
        expected = KIND_PREFIXES[enum_value(concept.kind)]
        if not separator or not local:
            issues.append(Issue(concept.id, "id must be a CURIE, e.g. permit:first-residence-permit"))
        elif prefix != expected:
            issues.append(Issue(concept.id, f"kind '{enum_value(concept.kind)}' requires the '{expected}:' prefix"))
    return issues


def _check_references(concepts: list[Concept], known: dict[str, Concept]) -> list[Issue]:
    """Every pointer must resolve, and an authority must be one."""
    issues: list[Issue] = []
    for concept in concepts:
        issues.extend(_unresolved_references(concept, known))
        issues.extend(_bad_authorities(concept, known))
    return issues


def _unresolved_references(concept: Concept, known: dict[str, Concept]) -> list[Issue]:
    """Report pointers that name nothing in the register, or that name their own concept."""
    issues: list[Issue] = []
    for slot in _REFERENCE_SLOTS:
        for target in getattr(concept, slot) or []:
            if target not in known:
                issues.append(Issue(concept.id, f"{slot} points at '{target}', which is not in the register"))
            elif target == concept.id:
                issues.append(Issue(concept.id, f"{slot} points at itself"))
    return issues


def _bad_authorities(concept: Concept, known: dict[str, Concept]) -> list[Issue]:
    """Report a ``handled_by`` that is not an organization, or was never in force alongside."""
    issues: list[Issue] = []
    for target in concept.handled_by or []:
        handler = known.get(target)
        if handler is None:
            continue
        if enum_value(handler.kind) != "organization":
            issues.append(Issue(concept.id, f"handled_by points at '{target}', which is not an organization"))
        elif not _overlap_in_force(concept, handler):
            # A service cannot have been handled by a body that had already
            # lapsed before it existed, or that only came into being after it
            # ended. Either the dates or the edge is wrong.
            issues.append(Issue(concept.id, f"handled_by '{target}' was never in force while this concept was"))
    return issues


def _check_validity(concepts: list[Concept], known: dict[str, Concept]) -> list[Issue]:
    """The rules that make a lapse legible: dated, explained, and handed over."""
    issues: list[Issue] = []
    for concept in concepts:
        if concept.valid_until is None:
            if concept.superseded_by:
                issues.append(Issue(concept.id, "superseded_by is set but valid_until is not"))
            continue
        issues.extend(_lapse_problems(concept))
        for target in concept.superseded_by or []:
            successor = known.get(target)
            if successor is not None:
                issues.extend(_handover_problems(concept, target, successor))
    return issues


def _lapse_problems(concept: Concept) -> list[Issue]:
    """Report a lapse that is misdated, or that neither points at a successor nor explains itself."""
    issues: list[Issue] = []
    if concept.valid_until is not None and concept.valid_until < concept.valid_from:
        issues.append(Issue(concept.id, "valid_until precedes valid_from"))
    if not concept.superseded_by and not (concept.change_note or "").strip():
        # Never delete, always supersede: an entity that left force either
        # points at what replaced it or says in writing that nothing did.
        issues.append(Issue(concept.id, "lapsed concept needs either superseded_by or a change_note"))
    return issues


def _handover_problems(concept: Concept, target: str, successor: Concept) -> list[Issue]:
    """Whether the successor was actually in force when this concept lapsed.

    G5 repairs a stale assertion by following this pointer, so a successor that
    had already lapsed, or had not yet begun, turns one validation failure into
    another.
    """
    if concept.valid_until is None:
        return []
    issues: list[Issue] = []
    if successor.valid_until is not None and successor.valid_until <= concept.valid_until:
        # `valid_until` is inclusive, so a successor lapsing on the same day was
        # never in force after the handover.
        issues.append(Issue(concept.id, f"superseded_by '{target}' did not outlast this concept"))
    # Subtracting rather than incrementing: `valid_until` can be `date.max`,
    # where adding a day overflows.
    if successor.valid_from - concept.valid_until > timedelta(days=1):
        issues.append(
            Issue(
                concept.id,
                f"superseded_by '{target}' only came into force on {successor.valid_from}, "
                f"leaving a gap after {concept.valid_until}",
            ),
        )
    return issues


def _reaches_itself(start: Concept, slot: str, known: dict[str, Concept]) -> bool:
    """Whether following ``slot`` from ``start`` leads back to ``start``.

    Only a path that returns to the starting concept is a cycle. Tracking every
    node visited instead would report one for a diamond - ``A`` broader ``B``
    and ``C``, both broader ``D`` - which is an ordinary shape in a hierarchy
    where a concept can have more than one parent. Every concept is checked, so
    a cycle anywhere is still found by whichever of its members starts.
    """
    expanded: set[str] = set()
    frontier = list(getattr(start, slot) or [])
    while frontier:
        current = frontier.pop()
        if current == start.id:
            return True
        if current in expanded:
            continue
        expanded.add(current)
        node = known.get(current)
        if node is not None:
            frontier.extend(getattr(node, slot) or [])
    return False


def _check_cycles(concepts: list[Concept], known: dict[str, Concept]) -> list[Issue]:
    """Reject cycles: in supersession they would make G5's auto-repair loop forever."""
    return [
        Issue(concept.id, f"{label} chain is cyclic")
        for slot, label in (("superseded_by", "supersession"), ("broader", "broader"))
        for concept in concepts
        if _reaches_itself(concept, slot, known)
    ]


def _surface_forms(concept: Concept) -> list[tuple[str, str]]:
    forms = [(language, getattr(concept.pref_label, language)) for language in ("en", "fi", "sv")]
    if concept.alt_labels is not None:
        for language in ("en", "fi", "sv"):
            forms.extend((language, label) for label in getattr(concept.alt_labels, language) or [])
    return forms


def _check_label_collisions(concepts: list[Concept]) -> list[Issue]:
    """A surface form must not resolve to two concepts that are in force together.

    The ``ground`` node maps spans of a user's message to IRIs by label alone,
    across every language the register carries, because a question can be asked
    in any of them and often mixes them. So the clash that matters is between
    surface forms, not between surface forms within one language: an English
    label on one concept and a Swedish label on another are just as ambiguous
    to a span matcher as two English ones.
    """
    by_form: dict[str, list[tuple[Concept, str]]] = defaultdict(list)
    for concept in concepts:
        for language, label in _surface_forms(concept):
            by_form[normalize_label(label)].append((concept, language))

    issues: list[Issue] = []
    for form, sharing in sorted(by_form.items()):
        if len(sharing) < _COLLISION:
            continue
        for index, (first, first_language) in enumerate(sharing):
            issues.extend(
                Issue(
                    first.id,
                    f"its {first_language} surface form '{form}' is also '{second.id}''s "
                    f"{second_language} label, while both are in force",
                )
                for second, second_language in sharing[index + 1 :]
                if second.id != first.id and _overlap_in_force(first, second)
            )
    return issues


def _overlap_in_force(first: Concept, second: Concept) -> bool:
    first_end = first.valid_until or date.max
    second_end = second.valid_until or date.max
    return first.valid_from <= second_end and second.valid_from <= first_end


def _check_label_shape(concepts: list[Concept]) -> list[Issue]:
    """A label is a term, not a sentence.

    A gloss that lands in a label is published as ``skos:prefLabel`` and becomes
    a surface form the ``ground`` node can match, so a parser that swept a
    definition into a label has to fail here rather than reach the graph.
    """
    issues: list[Issue] = []
    for concept in concepts:
        for language, label in _surface_forms(concept):
            if len(label) > _LABEL_MAX:
                issues.append(Issue(concept.id, f"{language} label is {len(label)} characters; it reads as a gloss"))
            elif ". " in label:
                issues.append(Issue(concept.id, f"{language} label '{label[:40]}...' contains sentence punctuation"))
    return issues


def _check_observations(concepts: list[Concept], register_version: date) -> list[Issue]:
    """Every concept records where it was seen, and every observation says where."""
    issues: list[Issue] = []
    for concept in concepts:
        if not concept.observations:
            issues.append(Issue(concept.id, "has no observations, so nothing records where it was seen"))
        if not concept.in_scope_of:
            issues.append(Issue(concept.id, "is in no guide's scope"))
        for observation in concept.observations:
            issues.extend(_observation_problems(concept, observation, register_version))
    return issues


def _observation_problems(concept: Concept, observation: Observation, register_version: date) -> list[Issue]:
    """Report an observation that names no publisher, postdates the edition, or cannot be opened."""
    issues: list[Issue] = []
    if enum_value(observation.source) == "other" and not (observation.note or "").strip():
        # `other` means the publisher has no entry of its own, so the note is
        # the only place the source is named at all.
        issues.append(Issue(concept.id, f"observation of {observation.url} uses 'other' without naming it"))
    if observation.observed_on > register_version:
        issues.append(Issue(concept.id, f"observed_on {observation.observed_on} is after the register version"))
    if not _is_resolvable_url(str(observation.url)):
        issues.append(Issue(concept.id, f"observation url '{observation.url}' is not a resolvable http(s) URL"))
    return issues


def _is_resolvable_url(url: str) -> bool:
    """Whether a URL names something a reader could actually open.

    A prefix test is not enough: the bare string ``https://`` starts with the
    scheme and points at nothing. Provenance that cannot be followed is not
    provenance, so the host has to be there too.
    """
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def check_publication(register: TermRegister) -> list[Issue]:
    """Check the SKOS an edition would publish, as a consumer would read it.

    The generated shapes validate the register in its own shape; this validates
    the projection of it that a consumer actually gets, which the shapes are not
    able to describe.
    """
    from tapio_register import skos

    return [Issue(None, problem) for problem in skos.check_graph(skos.to_graph(register))]


def check_integrity(register: TermRegister) -> list[Issue]:
    """Run every cross-concept rule and return the problems found."""
    concepts = list(register.concepts)
    known = {concept.id: concept for concept in concepts}
    return [
        *_check_identifiers(concepts),
        *_check_references(concepts, known),
        *_check_validity(concepts, known),
        *_check_cycles(concepts, known),
        *_check_label_collisions(concepts),
        *_check_label_shape(concepts),
        *_check_observations(concepts, register.register_version),
    ]


def summarize(register: TermRegister) -> dict[str, Any]:
    """Describe the register's coverage, for the CLI and the release manifest."""
    concepts = list(register.concepts)
    by_kind: dict[str, int] = defaultdict(int)
    by_guide: dict[str, int] = defaultdict(int)
    by_source: dict[str, int] = defaultdict(int)
    lapsed = 0
    aligned = 0
    for concept in concepts:
        by_kind[enum_value(concept.kind)] += 1
        for guide in concept.in_scope_of:
            by_guide[enum_value(guide)] += 1
        for observation in concept.observations:
            by_source[enum_value(observation.source)] += 1
        if concept.valid_until is not None:
            lapsed += 1
        if concept.exact_match or concept.close_match:
            aligned += 1
    return {
        "register_version": register.register_version.isoformat(),
        "concept_count": len(concepts),
        "lapsed_count": lapsed,
        "externally_aligned_count": aligned,
        "by_kind": dict(sorted(by_kind.items())),
        "by_guide": dict(sorted(by_guide.items())),
        "observations_by_source": dict(sorted(by_source.items())),
    }
