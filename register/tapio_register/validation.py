"""Checks the register has to pass before it can be released.

Three layers, cheapest first:

1. the generated Pydantic classes, which enforce the shape of each concept;
2. the generated JSON Schema and SHACL shapes, run through LinkML's validator,
   which is what proves the generated artifacts are usable and not just present;
3. the cross-concept rules below, which are what ADR 0007's "never delete,
   always supersede" and closed-world posture actually amount to in practice.

A rule enforced here is a rule a reviewer does not have to remember.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from tapio_register import paths
from tapio_register.generated.term_register_model import Concept, TermRegister
from tapio_register.loading import KIND_PREFIXES, enum_value, read_source

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
    merely present: the shapes checked here are the checked-in copies the
    harness's own gates G3 to G5 will load.
    """
    schema = str(schema_path or paths.SCHEMA_PATH)
    source = read_source(source_path)
    return [*_jsonschema_issues(schema, source), *_shacl_issues(schema, source)]


def _jsonschema_issues(schema: str, source: dict[str, Any]) -> list[Issue]:
    from linkml.validator import Validator
    from linkml.validator.plugins import JsonschemaValidationPlugin

    validator = Validator(schema=schema, validation_plugins=[JsonschemaValidationPlugin(closed=True)])
    report = validator.validate(source, target_class="TermRegister")
    return [Issue(None, result.message) for result in report.results]


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
    issues: list[Issue] = []
    for concept in concepts:
        for slot in _REFERENCE_SLOTS:
            for target in getattr(concept, slot) or []:
                if target not in known:
                    issues.append(Issue(concept.id, f"{slot} points at '{target}', which is not in the register"))
                elif target == concept.id:
                    issues.append(Issue(concept.id, f"{slot} points at itself"))
        for target in concept.handled_by or []:
            handler = known.get(target)
            if handler is not None and enum_value(handler.kind) != "organization":
                issues.append(Issue(concept.id, f"handled_by points at '{target}', which is not an organization"))
    return issues


def _check_validity(concepts: list[Concept], known: dict[str, Concept]) -> list[Issue]:
    issues: list[Issue] = []
    for concept in concepts:
        if concept.valid_until is None:
            if concept.superseded_by:
                issues.append(Issue(concept.id, "superseded_by is set but valid_until is not"))
            continue
        if concept.valid_until < concept.valid_from:
            issues.append(Issue(concept.id, "valid_until precedes valid_from"))
        if not concept.superseded_by and not concept.change_note:
            # Never delete, always supersede: an entity that left force either
            # points at what replaced it or says in writing that nothing did.
            issues.append(Issue(concept.id, "lapsed concept needs either superseded_by or a change_note"))
        for target in concept.superseded_by or []:
            successor = known.get(target)
            if successor is None:
                continue
            if successor.valid_until is not None and successor.valid_until < concept.valid_until:
                issues.append(Issue(concept.id, f"superseded_by '{target}' lapsed before this concept did"))
    return issues


def _check_supersession_chains(concepts: list[Concept], known: dict[str, Concept]) -> list[Issue]:
    """Reject cycles, which would make G5's auto-repair loop forever."""
    issues: list[Issue] = []
    for concept in concepts:
        seen = {concept.id}
        frontier = list(concept.superseded_by or [])
        while frontier:
            current = frontier.pop()
            if current in seen:
                issues.append(Issue(concept.id, "supersession chain is cyclic"))
                break
            seen.add(current)
            successor = known.get(current)
            if successor is not None:
                frontier.extend(successor.superseded_by or [])
    return issues


def _check_broader_chains(concepts: list[Concept], known: dict[str, Concept]) -> list[Issue]:
    issues: list[Issue] = []
    for concept in concepts:
        seen = {concept.id}
        frontier = list(concept.broader or [])
        while frontier:
            current = frontier.pop()
            if current in seen:
                issues.append(Issue(concept.id, "broader chain is cyclic"))
                break
            seen.add(current)
            parent = known.get(current)
            if parent is not None:
                frontier.extend(parent.broader or [])
    return issues


def _surface_forms(concept: Concept) -> list[tuple[str, str]]:
    forms = [(language, getattr(concept.pref_label, language)) for language in ("en", "fi", "sv")]
    if concept.alt_labels is not None:
        for language in ("en", "fi", "sv"):
            forms.extend((language, label) for label in getattr(concept.alt_labels, language) or [])
    return forms


def _check_label_collisions(concepts: list[Concept]) -> list[Issue]:
    """A surface form must not resolve to two concepts that are in force together.

    The ``ground`` node maps spans of a user's message to IRIs by label alone.
    Two live concepts sharing a label would make that mapping arbitrary, which
    is a register defect rather than a runtime one.
    """
    by_form: dict[tuple[str, str], list[Concept]] = defaultdict(list)
    for concept in concepts:
        for language, label in _surface_forms(concept):
            by_form[(language, normalize_label(label))].append(concept)

    issues: list[Issue] = []
    for (language, form), sharing in sorted(by_form.items()):
        if len(sharing) < _COLLISION:
            continue
        for index, first in enumerate(sharing):
            issues.extend(
                Issue(
                    first.id,
                    f"shares the {language} surface form '{form}' with '{second.id}' while both are in force",
                )
                for second in sharing[index + 1 :]
                if _overlap_in_force(first, second)
            )
    return issues


def _overlap_in_force(first: Concept, second: Concept) -> bool:
    first_end = first.valid_until or date.max
    second_end = second.valid_until or date.max
    return first.valid_from <= second_end and second.valid_from <= first_end


def _check_observations(concepts: list[Concept], register_version: date) -> list[Issue]:
    issues: list[Issue] = []
    for concept in concepts:
        for observation in concept.observations:
            if observation.observed_on > register_version:
                issues.append(
                    Issue(concept.id, f"observed_on {observation.observed_on} is after the register version"),
                )
            if not str(observation.url).startswith(("http://", "https://")):
                issues.append(Issue(concept.id, f"observation url '{observation.url}' is not an absolute URL"))
    return issues


def check_integrity(register: TermRegister) -> list[Issue]:
    """Run every cross-concept rule and return the problems found."""
    concepts = list(register.concepts)
    known = {concept.id: concept for concept in concepts}
    return [
        *_check_identifiers(concepts),
        *_check_references(concepts, known),
        *_check_validity(concepts, known),
        *_check_supersession_chains(concepts, known),
        *_check_broader_chains(concepts, known),
        *_check_label_collisions(concepts),
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
