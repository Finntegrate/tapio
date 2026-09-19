"""The published SKOS graph is what makes the register reusable outside Tapio."""

from datetime import date

from rdflib import URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS

from tapio_register.generated.term_register_model import TermRegister
from tapio_register.skos import SDO, TAPIO, in_force_on, to_graph

PERMIT = URIRef("https://tapio.finntegrate.org/register/permit/first-residence-permit")
BASE = URIRef("https://tapio.finntegrate.org/register/permit/residence-permit")


def test_concept_is_typed_as_skos_and_by_kind(register):
    graph = to_graph(register)
    assert (PERMIT, RDF.type, SKOS.Concept) in graph
    assert (PERMIT, RDF.type, TAPIO.Permit) in graph


def test_labels_are_language_tagged(register):
    graph = to_graph(register)
    languages = {literal.language for literal in graph.objects(PERMIT, SKOS.prefLabel)}
    assert languages == {"en", "fi", "sv"}


def test_relations_use_skos_predicates(register):
    graph = to_graph(register)
    assert (PERMIT, SKOS.broader, BASE) in graph
    assert (PERMIT, TAPIO.handledBy, URIRef("https://tapio.finntegrate.org/register/organization/migri")) in graph


def test_validity_and_supersession_are_published(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2025-01-01"
    register_dict["concepts"][1]["superseded_by"] = ["permit:first-residence-permit"]
    graph = to_graph(TermRegister.model_validate(register_dict))
    assert next(graph.objects(BASE, SDO.validFrom)).toPython() == date(2004, 5, 1)
    assert next(graph.objects(BASE, SDO.validThrough)).toPython() == date(2025, 1, 1)
    assert (BASE, DCTERMS.isReplacedBy, PERMIT) in graph


def test_observations_are_attached_to_the_concept(register):
    graph = to_graph(register)
    node = next(graph.objects(PERMIT, TAPIO.observation))
    assert (node, DCTERMS.source, URIRef("https://migri.fi/en/residence-permit")) in graph
    assert next(graph.objects(node, DCTERMS.date)).toPython() == date(2026, 9, 19)


def test_scheme_carries_the_coverage_caveat(register):
    graph = to_graph(register)
    scheme = URIRef("https://tapio.finntegrate.org/register/scheme")
    assert (scheme, RDF.type, SKOS.ConceptScheme) in graph
    assert (PERMIT, SKOS.inScheme, scheme) in graph
    assert "not ground truth" in str(next(graph.objects(scheme, RDFS.comment)))


def test_each_guide_gets_a_scope_collection(register):
    graph = to_graph(register)
    collection = URIRef("https://tapio.finntegrate.org/register/guide/ilmarinen")
    assert (collection, RDF.type, SKOS.Collection) in graph
    assert set(graph.objects(collection, SKOS.member)) == {
        URIRef(f"https://tapio.finntegrate.org/register/{part}")
        for part in ("permit/first-residence-permit", "permit/residence-permit", "organization/migri")
    }


def test_register_curies_survive_serialization(register):
    """rdflib pre-binds ``org:``; without an override the IRIs come back as ``org1:``."""
    turtle = to_graph(register).serialize(format="turtle")
    assert "org:migri" in turtle
    assert "org1:" not in turtle


def test_in_force_on_slices_by_date(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2020-12-31"
    register_dict["concepts"][1]["change_note"] = "Gone."
    register = TermRegister.model_validate(register_dict)
    live = {concept.id for concept in in_force_on(register, date(2026, 1, 1))}
    historical = {concept.id for concept in in_force_on(register, date(2019, 1, 1))}
    assert "permit:residence-permit" not in live
    assert "permit:residence-permit" in historical
