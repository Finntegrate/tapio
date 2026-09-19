"""Checks on the register that ships, rather than on a fixture.

These are the properties the milestone's later work depends on: that the shipped
register loads, that it obeys its own rules, that the entities the grounding
research found stale are modelled as stale, and that the released edition still
matches the source it was cut from.
"""

from datetime import date

import pytest

from tapio_register import loading, releasing, validation
from tapio_register.generated.term_register_model import TermRegister
from tapio_register.loading import enum_value
from tapio_register.skos import in_force_on, to_graph

#: Named in the grounding-source research as entities the corpus still refers to.
STALE = {
    "org:te-office": "org:municipal-employment-area",
    "org:ely-centre": "org:economic-development-centre",
    "org:municipal-health-and-social-services": "org:wellbeing-services-county",
}


@pytest.fixture(scope="module")
def shipped() -> TermRegister:
    return loading.load_register()


def test_register_loads_and_obeys_its_own_rules(shipped):
    assert [str(issue) for issue in validation.check_integrity(shipped)] == []
    assert len(shipped.concepts) >= 100


def test_scoped_to_ilmarinens_domain(shipped):
    by_guide = validation.summarize(shipped)["by_guide"]
    assert by_guide["ilmarinen"] >= 100


def test_every_concept_carries_three_languages_and_provenance(shipped):
    for concept in shipped.concepts:
        assert concept.pref_label.en
        assert concept.pref_label.fi
        assert concept.pref_label.sv
        assert concept.observations
        for observation in concept.observations:
            # YSO's canonical IRIs are http, so absolute is the requirement, not https.
            assert str(observation.url).startswith(("https://", "http://"))
            assert observation.observed_on <= shipped.register_version


@pytest.mark.parametrize(("stale_id", "successor_id"), sorted(STALE.items()))
def test_known_stale_entity_is_superseded(shipped, stale_id, successor_id):
    concepts = loading.concepts_by_id(shipped)
    stale = concepts[stale_id]
    assert stale.valid_until is not None
    assert stale.superseded_by == [successor_id]
    assert stale.change_note
    successor = concepts[successor_id]
    assert successor.valid_from > stale.valid_until
    assert successor.valid_until is None


def test_a_stale_entity_is_not_in_force_today_but_was_before(shipped):
    concepts = loading.concepts_by_id(shipped)
    te_office = concepts["org:te-office"]
    assert te_office not in in_force_on(shipped, shipped.register_version)
    assert te_office in in_force_on(shipped, date(2024, 6, 1))


def test_ids_use_the_prefix_their_kind_requires(shipped):
    for concept in shipped.concepts:
        assert concept.id.split(":")[0] == loading.KIND_PREFIXES[enum_value(concept.kind)]


def test_register_is_aligned_to_published_vocabularies(shipped):
    aligned = [c for c in shipped.concepts if c.exact_match or c.close_match]
    assert aligned
    for concept in aligned:
        for match in (concept.exact_match or []) + (concept.close_match or []):
            assert match.startswith("yso:")


def test_shipped_register_publishes_as_skos(shipped):
    graph = to_graph(shipped)
    assert len(graph) > len(shipped.concepts)


def test_the_released_edition_matches_its_manifest():
    assert releasing.verify_releases() == []


def test_an_edition_exists_for_the_source_version(shipped):
    assert shipped.register_version.isoformat() in releasing.released_versions()


def test_the_source_still_matches_the_edition_it_names():
    assert releasing.verify_source_edition() == []
