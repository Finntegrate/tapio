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
