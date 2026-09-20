"""The two shapes a model consumes: options to pick from, facts to generate against."""

from datetime import date

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


def test_facts_name_the_handling_authority(register):
    rendered = projection.facts(register, ["permit:first-residence-permit"])
    assert rendered[0]["handled_by"] == ["org:migri"]


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
    assert "No longer in force since 2024-12-31" in block
    assert "Replaced by: employment area" in block


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
