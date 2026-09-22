"""The register read as a record of change: what was true then, and what stands now."""

from datetime import date

from tapio_register import history, loading
from tapio_register.generated.term_register_model import TermRegister


def test_in_force_on_slices_by_date(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2020-12-31"
    register_dict["concepts"][1]["change_note"] = "Gone."
    register = TermRegister.model_validate(register_dict)
    live = {concept.id for concept in history.in_force_on(register, date(2026, 1, 1))}
    historical = {concept.id for concept in history.in_force_on(register, date(2019, 1, 1))}
    assert "permit:residence-permit" not in live
    assert "permit:residence-permit" in historical


def test_valid_until_is_inclusive(register_dict):
    """A body dissolved on 1 January is still in force on 31 December."""
    register_dict["concepts"][1]["valid_until"] = "2024-12-31"
    register_dict["concepts"][1]["change_note"] = "Gone."
    register = TermRegister.model_validate(register_dict)
    assert any(c.id == "permit:residence-permit" for c in history.in_force_on(register, date(2024, 12, 31)))
    assert not any(c.id == "permit:residence-permit" for c in history.in_force_on(register, date(2025, 1, 1)))


def test_lineage_follows_a_name_forward_to_what_stands_in_its_place():
    """The recollection a long-serving colleague would have about a 2018 document."""
    shipped = loading.load_register()
    chain = history.lineage(shipped, "org:te-office")
    assert [c.id for c in chain] == ["org:te-office", "org:municipal-employment-area"]
    assert chain[0].valid_until is not None
    assert chain[-1].valid_until is None


def test_lineage_of_something_still_in_force_is_itself(register):
    assert [c.id for c in history.lineage(register, "org:migri")] == ["org:migri"]


def test_lineage_of_an_unknown_concept_is_empty(register):
    assert history.lineage(register, "permit:never-existed") == []


def test_lineage_stops_rather_than_looping(register_dict):
    """Validation rejects supersession cycles; this must not hang if one slips through."""
    first, second = register_dict["concepts"][0], register_dict["concepts"][1]
    first["valid_until"] = second["valid_until"] = "2025-01-01"
    first["superseded_by"] = [second["id"]]
    second["superseded_by"] = [first["id"]]
    register = TermRegister.model_validate(register_dict)
    assert len(history.lineage(register, first["id"])) == 2
