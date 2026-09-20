"""The two shapes a model consumes: options to pick from, facts to generate against."""

from datetime import date

from conftest import concept

from tapio_register import loading, projection
from tapio_register.generated.term_register_model import TermRegister


def test_options_are_one_line_per_concept(register):
    chosen = projection.options(register)
    assert chosen["org:migri"] == "org:migri / org:migri fi / org:migri sv"
    assert len(chosen) == 3


def test_options_scope_to_one_guide(register_dict):
    register_dict["concepts"][2]["in_scope_of"] = ["otso"]
    register = TermRegister.model_validate(register_dict)
    assert "org:migri" not in projection.options(register, guide="ilmarinen")
    assert "org:migri" in projection.options(register, guide="otso")


def test_options_can_be_limited_to_kinds(register):
    assert set(projection.options(register, kinds=["organization"])) == {"org:migri"}


def test_a_lapsed_concept_is_offered_but_marked(register_dict):
    """Someone asking about the TE Office should be recognised, then redirected."""
    register_dict["concepts"][1]["valid_until"] = "2024-12-31"
    register_dict["concepts"][1]["change_note"] = "Gone."
    register = TermRegister.model_validate(register_dict)
    assert "(until 2024-12-31)" in projection.options(register)["permit:residence-permit"]
    assert "permit:residence-permit" not in projection.options(register, include_lapsed=False)


def test_facts_cover_only_the_concepts_asked_for(register):
    rendered = projection.facts(register, ["org:migri", "permit:never-existed"])
    assert [f["id"] for f in rendered] == ["org:migri"]
    assert rendered[0]["in_force"] is True
    assert rendered[0]["kind"] == "organization"


def test_facts_name_the_handling_authority_in_every_language(register):
    """A guide answering in Finnish needs the authority's Finnish name, not a gloss."""
    rendered = projection.facts(register, ["permit:first-residence-permit"])
    (authority,) = rendered[0]["handled_by"]
    assert authority["id"] == "org:migri"
    assert authority["labels"] == {"en": "org:migri", "fi": "org:migri fi", "sv": "org:migri sv"}


def test_facts_for_a_lapsed_concept_carry_what_replaced_it():
    """The useful answer to "where is my TE Office" names the body that took over."""
    shipped = loading.load_register()
    fact = projection.facts(shipped, ["org:te-office"])[0]
    assert fact["in_force"] is False
    assert fact["lapsed_on"] == date(2024, 12, 31)
    assert [r["id"] for r in fact["replaced_by"]] == ["org:municipal-employment-area"]
    assert "transferred" in fact["what_changed"]


def test_facts_answer_as_of_a_past_date():
    shipped = loading.load_register()
    assert projection.facts(shipped, ["org:te-office"], reference=date(2018, 6, 1))[0]["in_force"] is True


def test_the_prompt_block_says_what_lapsed_and_what_replaced_it():
    shipped = loading.load_register()
    block = projection.as_prompt_block(projection.facts(shipped, ["org:te-office"]))
    # valid_until is inclusive, so the office was still there on 2024-12-31.
    assert "In force through 2024-12-31, not after." in block
    assert "Replaced by: " in block
    assert "employment area" in block


def test_the_prompt_block_names_authorities_in_the_answering_language():
    shipped = loading.load_register()
    facts = projection.facts(shipped, ["step:apply-for-asylum"])
    assert "Rajavartiolaitos" in projection.as_prompt_block(facts, language="fi")
    assert "Gränsbevakningsväsendet" in projection.as_prompt_block(facts, language="sv")


def test_a_concept_split_across_several_bodies_names_all_of_them(register_dict):
    """Picking one successor would make the answer depend on YAML order."""
    register_dict["concepts"][1]["valid_until"] = "2024-12-31"
    register_dict["concepts"][1]["superseded_by"] = ["permit:first-residence-permit", "org:migri"]
    register = TermRegister.model_validate(register_dict)
    (fact,) = projection.facts(register, ["permit:residence-permit"])
    assert "replaced_by" not in fact
    assert [entry["id"] for entry in fact["split_into"]] == ["permit:first-residence-permit", "org:migri"]
    assert "Its work was split across:" in projection.as_prompt_block([fact])


def test_one_guides_options_fit_in_a_prompt():
    """The whole point: a curated file a model can actually be shown."""
    chosen = projection.options(loading.load_register(), guide="ilmarinen")
    assert len(chosen) > 100
    assert sum(len(k) + len(v) for k, v in chosen.items()) < 20_000


def test_a_concept_ending_in_the_future_is_still_offered(register_dict):
    """An end date is not a lapse until it arrives, and --current-only must not hide it."""
    register_dict["concepts"][1]["valid_until"] = "2099-12-31"
    register = TermRegister.model_validate(register_dict)
    chosen = projection.options(register, include_lapsed=False)
    assert "(until 2099-12-31)" in chosen["permit:residence-permit"]


def test_a_concept_not_yet_in_force_is_marked_and_filtered(register_dict):
    register_dict["concepts"][1]["valid_from"] = "2099-01-01"
    register = TermRegister.model_validate(register_dict)
    assert "(from 2099-01-01)" in projection.options(register)["permit:residence-permit"]
    assert "permit:residence-permit" not in projection.options(register, include_lapsed=False)


def test_options_read_validity_at_a_reference_date(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2024-12-31"
    register = TermRegister.model_validate(register_dict)
    on_the_day = projection.options(register, include_lapsed=False, reference=date(2024, 6, 1))
    assert "permit:residence-permit" in on_the_day
    after = projection.options(register, include_lapsed=False, reference=date(2025, 6, 1))
    assert "permit:residence-permit" not in after


def test_facts_read_the_start_of_validity_too(register_dict):
    """A concept that had not started yet is not in force, and has not been superseded."""
    register_dict["concepts"][1]["valid_from"] = "2024-01-01"
    register = TermRegister.model_validate(register_dict)
    (fact,) = projection.facts(register, ["permit:residence-permit"], reference=date(2023, 1, 1))
    assert fact["in_force"] is False
    assert fact["in_force_from"] == date(2024, 1, 1)
    assert "lapsed_on" not in fact
    assert "Not in force until 2024-01-01." in projection.as_prompt_block([fact])


def test_facts_call_a_future_end_date_in_force(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2099-12-31"
    register = TermRegister.model_validate(register_dict)
    (fact,) = projection.facts(register, ["permit:residence-permit"])
    assert fact["in_force"] is True
    assert "lapsed_on" not in fact


def _chain(register_dict, concept_factory):
    """A -> B -> C, each replacing the last: te-office style, two handovers deep."""
    register_dict["concepts"] = [
        concept_factory(
            "org:a", kind="organization", valid_from="2000-01-01", valid_until="2010-12-31", superseded_by=["org:b"]
        ),
        concept_factory(
            "org:b", kind="organization", valid_from="2011-01-01", valid_until="2020-12-31", superseded_by=["org:c"]
        ),
        concept_factory("org:c", kind="organization", valid_from="2021-01-01"),
    ]
    return TermRegister.model_validate(register_dict)


def test_supersession_is_read_at_the_reference_date_not_today(register_dict):
    """Naming C for a date when B still stood is a fact about now dressed as one about then."""
    register = _chain(register_dict, concept)
    (then,) = projection.facts(register, ["org:a"], reference=date(2015, 6, 1))
    assert [e["id"] for e in then["replaced_by"]] == ["org:b"]
    (now,) = projection.facts(register, ["org:a"], reference=date(2026, 6, 1))
    assert [e["id"] for e in now["replaced_by"]] == ["org:b", "org:c"]


def test_a_successor_that_did_not_exist_yet_is_not_named(register_dict):
    register = _chain(register_dict, concept)
    (fact,) = projection.facts(register, ["org:b"], reference=date(2020, 12, 31))
    # B lapses on 2020-12-31 and C only exists from 2021-01-01.
    assert fact["in_force"] is True
    (after,) = projection.facts(register, ["org:b"], reference=date(2021, 6, 1))
    assert [e["id"] for e in after["replaced_by"]] == ["org:c"]


def test_a_handler_not_in_force_on_the_date_is_not_reported_as_handling(register_dict):
    """Otherwise a 2018 answer names a body that did not exist until 2025."""
    register_dict["concepts"][2]["valid_from"] = "2025-01-01"
    register = TermRegister.model_validate(register_dict)
    (then,) = projection.facts(register, ["permit:first-residence-permit"], reference=date(2018, 1, 1))
    assert "handled_by" not in then
    (now,) = projection.facts(register, ["permit:first-residence-permit"], reference=date(2026, 1, 1))
    assert [e["id"] for e in now["handled_by"]] == ["org:migri"]
