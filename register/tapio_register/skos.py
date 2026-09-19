"""Publish the register as versioned SKOS.

Published as SKOS rather than in the register's own shape so that it composes
with the Finnish vocabulary infrastructure it aligns to (Finto, JUPO, PTV)
instead of sitting beside it.
"""

import json
from datetime import date
from typing import Any

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS, XSD

from tapio_register.generated.term_register_model import Concept, TermRegister
from tapio_register.loading import (
    GUIDE_COLLECTION_BASE,
    PREFIX_NAMESPACES,
    SCHEME_IRI,
    TAPIO_NAMESPACE,
    enum_value,
    expand,
)

TAPIO = Namespace(TAPIO_NAMESPACE)
SDO = Namespace("https://schema.org/")

#: An RDF class per concept kind, so a consumer can ask for organizations
#: alone without reading the register's own enum.
KIND_CLASSES = {
    "organization": TAPIO.Organization,
    "permit": TAPIO.Permit,
    "step": TAPIO.ProcessStep,
    "document": TAPIO.Document,
    "status": TAPIO.LegalStatus,
    "service": TAPIO.Service,
    "legal_act": TAPIO.LegalAct,
    "term": TAPIO.Term,
}

_LANGUAGES = ("en", "fi", "sv")


def _bind(graph: Graph) -> None:
    graph.bind("skos", SKOS)
    graph.bind("dcterms", DCTERMS)
    graph.bind("sdo", SDO)
    graph.bind("tapio", TAPIO)
    for prefix, namespace in PREFIX_NAMESPACES.items():
        # ``override``/``replace``: rdflib already binds some of these prefixes
        # (``org`` to the W3C Organization ontology), and without this it
        # silently renames ours to ``org1``, so the register's own CURIEs would
        # not round-trip.
        graph.bind(prefix, Namespace(namespace), override=True, replace=True)


def _add_scheme(graph: Graph, register: TermRegister) -> URIRef:
    scheme = URIRef(SCHEME_IRI)
    graph.add((scheme, RDF.type, SKOS.ConceptScheme))
    graph.add((scheme, DCTERMS.title, Literal(register.title, lang="en")))
    graph.add((scheme, DCTERMS.description, Literal(register.description, lang="en")))
    graph.add((scheme, DCTERMS.license, Literal(register.license)))
    graph.add((scheme, DCTERMS.issued, Literal(register.register_version, datatype=XSD.date)))
    graph.add((scheme, DCTERMS.hasVersion, Literal(register.register_version.isoformat())))
    # Published with every edition, not only in the repository: a dataset about
    # administrative change that overstates its completeness is worse than none.
    graph.add((scheme, RDFS.comment, Literal(register.coverage_caveat, lang="en")))
    return scheme


def _add_labels(graph: Graph, subject: URIRef, concept: Concept) -> None:
    for language in _LANGUAGES:
        graph.add((subject, SKOS.prefLabel, Literal(getattr(concept.pref_label, language), lang=language)))
        if concept.alt_labels is not None:
            for label in getattr(concept.alt_labels, language) or []:
                graph.add((subject, SKOS.altLabel, Literal(label, lang=language)))
        if concept.definition is not None:
            definition = getattr(concept.definition, language)
            if definition:
                graph.add((subject, SKOS.definition, Literal(definition, lang=language)))


def _add_validity(graph: Graph, subject: URIRef, concept: Concept) -> None:
    graph.add((subject, SDO.validFrom, Literal(concept.valid_from, datatype=XSD.date)))
    if concept.valid_until is not None:
        graph.add((subject, SDO.validThrough, Literal(concept.valid_until, datatype=XSD.date)))
    for successor in concept.superseded_by or []:
        graph.add((subject, DCTERMS.isReplacedBy, URIRef(expand(successor))))
    if concept.change_note:
        graph.add((subject, SKOS.changeNote, Literal(concept.change_note, lang="en")))


def _add_relations(graph: Graph, subject: URIRef, concept: Concept) -> None:
    for target in concept.broader or []:
        graph.add((subject, SKOS.broader, URIRef(expand(target))))
    for target in concept.related or []:
        graph.add((subject, SKOS.related, URIRef(expand(target))))
    for target in concept.handled_by or []:
        graph.add((subject, TAPIO.handledBy, URIRef(expand(target))))
    for target in concept.exact_match or []:
        graph.add((subject, SKOS.exactMatch, URIRef(expand(target))))
    for target in concept.close_match or []:
        graph.add((subject, SKOS.closeMatch, URIRef(expand(target))))


def _add_observations(graph: Graph, subject: URIRef, concept: Concept) -> None:
    for index, observation in enumerate(concept.observations, start=1):
        # An IRI rather than a blank node, for two reasons: an observation is
        # something a reader may want to cite ("where did you see that, and
        # when"), and blank node labels are regenerated on every serialization,
        # which would make a released edition's bytes unreproducible.
        node = URIRef(f"{subject}#observation-{index}")
        graph.add((subject, TAPIO.observation, node))
        graph.add((node, RDF.type, TAPIO.Observation))
        graph.add((node, DCTERMS.publisher, Literal(enum_value(observation.source))))
        graph.add((node, DCTERMS.source, URIRef(str(observation.url))))
        graph.add((node, DCTERMS.date, Literal(observation.observed_on, datatype=XSD.date)))
        if observation.note:
            graph.add((node, RDFS.comment, Literal(observation.note, lang="en")))


def _add_guide_collections(graph: Graph, register: TermRegister) -> None:
    """One ``skos:Collection`` per guide: the concept set gate G3 checks against."""
    members: dict[str, list[URIRef]] = {}
    for concept in register.concepts:
        for guide in concept.in_scope_of:
            members.setdefault(enum_value(guide), []).append(URIRef(expand(concept.id)))
    for guide_id, concepts in sorted(members.items()):
        collection = URIRef(f"{GUIDE_COLLECTION_BASE}{guide_id}")
        graph.add((collection, RDF.type, SKOS.Collection))
        graph.add((collection, SKOS.prefLabel, Literal(f"{guide_id.capitalize()} scope", lang="en")))
        for concept_iri in concepts:
            graph.add((collection, SKOS.member, concept_iri))


def to_graph(register: TermRegister) -> Graph:
    """Render one edition of the register as a SKOS graph."""
    graph = Graph()
    _bind(graph)
    scheme = _add_scheme(graph, register)
    for concept in register.concepts:
        subject = URIRef(expand(concept.id))
        graph.add((subject, RDF.type, SKOS.Concept))
        graph.add((subject, RDF.type, KIND_CLASSES[enum_value(concept.kind)]))
        graph.add((subject, SKOS.inScheme, scheme))
        if concept.notation:
            graph.add((subject, SKOS.notation, Literal(concept.notation)))
        _add_labels(graph, subject, concept)
        _add_validity(graph, subject, concept)
        _add_relations(graph, subject, concept)
        _add_observations(graph, subject, concept)
    _add_guide_collections(graph, register)
    return graph


def _canonical(node: Any) -> Any:
    """Order a parsed JSON-LD document so equal graphs render identically."""
    if isinstance(node, list):
        items = [_canonical(item) for item in node]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    if isinstance(node, dict):
        return {key: _canonical(value) for key, value in sorted(node.items())}
    return node


def serialize(graph: Graph, rdf_format: str) -> str:
    """Serialize a register graph reproducibly.

    A dated edition's digest is only meaningful if the same register always
    produces the same bytes. rdflib orders Turtle deterministically once blank
    nodes are out of the way, but its JSON-LD writer does not, so that one is
    re-emitted in a canonical order.
    """
    text = graph.serialize(format=rdf_format, auto_compact=True)
    if rdf_format == "json-ld":
        text = json.dumps(_canonical(json.loads(text)), indent=2, ensure_ascii=False, sort_keys=True)
    return text if text.endswith("\n") else text + "\n"


def in_force_on(register: TermRegister, reference: date) -> list[Concept]:
    """Return the concepts in force on ``reference``.

    This is the time slice gate G5 reads, and the same operation that makes
    "what applied when I arrived" answerable from a dated edition.
    """
    return [
        concept
        for concept in register.concepts
        if concept.valid_from <= reference and (concept.valid_until is None or concept.valid_until >= reference)
    ]
