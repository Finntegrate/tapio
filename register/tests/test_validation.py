"""The cross-concept rules are what ADR 0007's posture amounts to in practice."""

import pytest
from pydantic import ValidationError

from tapio_register.generated.term_register_model import TermRegister
from tapio_register.validation import check_integrity, normalize_label, summarize
from tests.conftest import concept


def messages(register_dict: dict) -> list[str]:
    return [str(issue) for issue in check_integrity(TermRegister.model_validate(register_dict))]


def test_valid_register_has_no_issues(register):
    assert check_integrity(register) == []


def test_id_prefix_must_match_kind(register_dict):
    register_dict["concepts"].append(concept("permit:migri-office", kind="organization"))
    assert any("requires the 'org:' prefix" in message for message in messages(register_dict))


def test_id_must_be_a_curie(register_dict):
    register_dict["concepts"].append(concept("residence-permit"))
    assert any("must be a CURIE" in message for message in messages(register_dict))


def test_duplicate_ids_are_rejected(register_dict):
    register_dict["concepts"].append(concept("permit:residence-permit"))
    assert any("duplicate concept id" in message for message in messages(register_dict))


def test_dangling_reference_is_rejected(register_dict):
    register_dict["concepts"][0]["related"] = ["permit:does-not-exist"]
    assert any("not in the register" in message for message in messages(register_dict))


def test_self_reference_is_rejected(register_dict):
    register_dict["concepts"][0]["related"] = ["permit:first-residence-permit"]
    assert any("points at itself" in message for message in messages(register_dict))


def test_handled_by_must_point_at_an_organization(register_dict):
    register_dict["concepts"][0]["handled_by"] = ["permit:residence-permit"]
    assert any("not an organization" in message for message in messages(register_dict))


def test_lapsed_concept_needs_a_successor_or_an_explanation(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2025-01-01"
    assert any("superseded_by or a change_note" in message for message in messages(register_dict))


def test_lapsed_concept_may_explain_itself_instead(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2025-01-01"
    register_dict["concepts"][1]["change_note"] = "Abolished outright; nothing replaced it."
    assert messages(register_dict) == []


def test_superseded_by_without_valid_until_is_rejected(register_dict):
    register_dict["concepts"][1]["superseded_by"] = ["permit:first-residence-permit"]
    assert any("superseded_by is set but valid_until is not" in message for message in messages(register_dict))


def test_valid_until_before_valid_from_is_rejected(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2000-01-01"
    register_dict["concepts"][1]["change_note"] = "Backdated by mistake."
    assert any("valid_until precedes valid_from" in message for message in messages(register_dict))


def test_successor_may_not_have_lapsed_first(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2025-01-01"
    register_dict["concepts"][1]["superseded_by"] = ["permit:first-residence-permit"]
    register_dict["concepts"][0]["valid_until"] = "2020-01-01"
    register_dict["concepts"][0]["change_note"] = "Gone."
    assert any("did not outlast this concept" in message for message in messages(register_dict))


def test_a_successor_lapsing_on_the_same_day_is_rejected(register_dict):
    """`valid_until` is inclusive, so it was never in force after the handover."""
    register_dict["concepts"][1]["valid_until"] = "2025-01-01"
    register_dict["concepts"][1]["superseded_by"] = ["permit:first-residence-permit"]
    register_dict["concepts"][0]["valid_until"] = "2025-01-01"
    register_dict["concepts"][0]["change_note"] = "Also gone, the same day."
    assert any("did not outlast this concept" in message for message in messages(register_dict))


def test_supersession_cycle_is_rejected(register_dict):
    first, second = register_dict["concepts"][0], register_dict["concepts"][1]
    first["valid_until"] = second["valid_until"] = "2025-01-01"
    first["superseded_by"] = [second["id"]]
    second["superseded_by"] = [first["id"]]
    assert any("supersession chain is cyclic" in message for message in messages(register_dict))


def test_a_diamond_is_not_a_cycle(register_dict):
    """Two parents sharing a grandparent is an ordinary hierarchy, not a defect."""
    register_dict["concepts"].append(
        concept(
            "permit:shared-parent",
            pref_label={"en": "shared parent", "fi": "yhteinen", "sv": "gemensam"},
        ),
    )
    register_dict["concepts"][0]["broader"] = ["permit:residence-permit", "org:migri"]
    register_dict["concepts"][1]["broader"] = ["permit:shared-parent"]
    register_dict["concepts"][2]["broader"] = ["permit:shared-parent"]
    assert not [message for message in messages(register_dict) if "cyclic" in message]


def test_a_successor_that_leaves_a_gap_is_rejected(register_dict):
    """G5 repairs through this pointer, so the successor must already be in force."""
    register_dict["concepts"][1]["valid_until"] = "2025-01-01"
    register_dict["concepts"][1]["superseded_by"] = ["permit:first-residence-permit"]
    register_dict["concepts"][0]["valid_from"] = "2026-01-01"
    assert any("leaving a gap after" in message for message in messages(register_dict))


def test_a_successor_taking_over_the_next_day_is_accepted(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2024-12-31"
    register_dict["concepts"][1]["superseded_by"] = ["permit:first-residence-permit"]
    register_dict["concepts"][0]["valid_from"] = "2025-01-01"
    assert messages(register_dict) == []


def test_an_authority_never_in_force_alongside_the_concept_is_rejected(register_dict):
    register_dict["concepts"][2]["valid_until"] = "2010-01-01"
    register_dict["concepts"][2]["change_note"] = "Long gone."
    register_dict["concepts"][0]["valid_from"] = "2020-01-01"
    assert any("was never in force while this concept was" in message for message in messages(register_dict))


def test_a_label_carrying_a_definition_is_rejected(register_dict):
    """A gloss swept into a label is published as a prefLabel and matched by ground."""
    register_dict["concepts"][0]["pref_label"]["sv"] = "internationellt skydd " + "x" * 120
    assert any("reads as a gloss" in message for message in messages(register_dict))


def test_a_label_containing_sentence_punctuation_is_rejected(register_dict):
    register_dict["concepts"][0]["pref_label"]["en"] = "Residence permit. Issued by Migri"
    assert any("sentence punctuation" in message for message in messages(register_dict))


def test_an_unnamed_other_source_is_rejected(register_dict):
    """`other` means the publisher has no entry, so the note is the only record of it."""
    register_dict["concepts"][0]["observations"][0]["source"] = "other"
    assert any("uses 'other' without naming it" in message for message in messages(register_dict))


def test_a_named_other_source_is_accepted(register_dict):
    register_dict["concepts"][0]["observations"][0]["source"] = "other"
    register_dict["concepts"][0]["observations"][0]["note"] = "Ministry of Finance."
    assert messages(register_dict) == []


def test_a_concept_with_no_provenance_is_rejected_by_the_schema(register_dict):
    """`required` alone lets an empty list through; minimum_cardinality is the guard."""
    register_dict["concepts"][0]["observations"] = []
    with pytest.raises(ValidationError):
        TermRegister.model_validate(register_dict)


def test_a_concept_in_no_guides_scope_is_rejected_by_the_schema(register_dict):
    register_dict["concepts"][0]["in_scope_of"] = []
    with pytest.raises(ValidationError):
        TermRegister.model_validate(register_dict)


def test_broader_cycle_is_rejected(register_dict):
    register_dict["concepts"][1]["broader"] = ["permit:first-residence-permit"]
    assert any("broader chain is cyclic" in message for message in messages(register_dict))


def test_label_shared_by_two_live_concepts_is_rejected(register_dict):
    register_dict["concepts"][1]["pref_label"]["fi"] = register_dict["concepts"][0]["pref_label"]["fi"]
    assert any("while both are in force" in message for message in messages(register_dict))


def test_alt_label_colliding_with_a_pref_label_is_rejected(register_dict):
    register_dict["concepts"][1]["alt_labels"] = {"en": ["permit:first-residence-permit"]}
    assert any("while both are in force" in message for message in messages(register_dict))


def test_a_collision_across_two_languages_is_rejected(register_dict):
    """`ground` matches a span against every language, so the clash is between forms."""
    register_dict["concepts"][1]["pref_label"]["sv"] = register_dict["concepts"][0]["pref_label"]["en"]
    assert any("is also" in message and "while both are in force" in message for message in messages(register_dict))


def test_label_reuse_is_allowed_once_the_earlier_concept_has_lapsed(register_dict):
    earlier, later = register_dict["concepts"][0], register_dict["concepts"][1]
    earlier["valid_until"] = "2020-12-31"
    earlier["change_note"] = "Renamed."
    later["valid_from"] = "2021-01-01"
    later["pref_label"] = dict(earlier["pref_label"])
    assert messages(register_dict) == []


def test_observation_may_not_postdate_the_register_version(register_dict):
    register_dict["concepts"][0]["observations"][0]["observed_on"] = "2027-01-01"
    assert any("is after the register version" in message for message in messages(register_dict))


def test_observation_url_must_be_absolute(register_dict):
    register_dict["concepts"][0]["observations"][0]["url"] = "/en/residence-permit"
    assert any("not a resolvable http(s) URL" in message for message in messages(register_dict))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  Oleskelulupa ", "oleskelulupa"), ("EU Blue\tCard", "eu blue card"), ("Ensimmäinen", "ensimmäinen")],
)
def test_normalize_label_folds_case_and_whitespace_only(raw, expected):
    assert normalize_label(raw) == expected


def test_summary_counts_what_the_register_covers(register):
    summary = summarize(register)
    assert summary["concept_count"] == 3
    assert summary["by_kind"] == {"organization": 1, "permit": 2}
    assert summary["by_guide"] == {"ilmarinen": 3}
    assert summary["observations_by_source"] == {"migri": 3}


def test_shipped_schema_and_shapes_accept_a_well_formed_register(tmp_path, register_dict):
    """Slow, and the point: it runs the checked-in JSON Schema and SHACL shapes."""
    import yaml

    from tapio_register.validation import check_schema

    path = tmp_path / "register.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    assert check_schema(path) == []


def test_shipped_schema_rejects_an_empty_label(tmp_path, register_dict):
    """An empty label satisfies `required` but gives ground no surface form to match."""
    import yaml

    from tapio_register.validation import check_schema

    register_dict["concepts"][0]["pref_label"]["sv"] = "   "
    path = tmp_path / "register.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    assert any("pref_label/sv" in str(issue) for issue in check_schema(path))


def test_shipped_schema_rejects_a_concept_with_no_provenance(tmp_path, register_dict):
    import yaml

    from tapio_register.validation import check_schema

    register_dict["concepts"][0]["observations"] = []
    path = tmp_path / "register.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    assert any("observations" in str(issue) for issue in check_schema(path))


def test_shipped_schema_and_shapes_reject_an_unknown_kind(tmp_path, register_dict):
    import yaml

    from tapio_register.validation import check_schema

    register_dict["concepts"][0]["kind"] = "not-a-kind"
    path = tmp_path / "register.yaml"
    path.write_text(yaml.safe_dump(register_dict, allow_unicode=True), encoding="utf-8")
    issues = [str(issue) for issue in check_schema(path)]
    assert any("is not one of" in issue for issue in issues)
    assert any("could not be converted to RDF" in issue for issue in issues)


def test_a_whitespace_only_note_names_no_publisher(register_dict):
    """Blank is as absent as missing, for a field whose whole job is to name a source."""
    register_dict["concepts"][0]["observations"][0]["source"] = "other"
    register_dict["concepts"][0]["observations"][0]["note"] = "   "
    assert any("uses 'other' without naming it" in message for message in messages(register_dict))


def test_a_whitespace_only_change_note_explains_nothing(register_dict):
    register_dict["concepts"][1]["valid_until"] = "2025-01-01"
    register_dict["concepts"][1]["change_note"] = "  "
    assert any("superseded_by or a change_note" in message for message in messages(register_dict))


def test_a_concept_in_force_until_the_maximum_date_does_not_overflow(register_dict):
    """`valid_until + one day` raises OverflowError at date.max; the check subtracts instead."""
    register_dict["concepts"][1]["valid_until"] = "9999-12-31"
    register_dict["concepts"][1]["superseded_by"] = ["permit:first-residence-permit"]
    reported = messages(register_dict)
    assert not [message for message in reported if "leaving a gap" in message]


@pytest.mark.parametrize("url", ["https://", "http://", "https:///path", "not-a-url", "ftp://migri.fi"])
def test_an_observation_url_that_resolves_to_nothing_is_rejected(register_dict, url):
    """A prefix test passes `https://`, which points at nothing a reader could open."""
    register_dict["concepts"][0]["observations"][0]["url"] = url
    assert any("not a resolvable http(s) URL" in message for message in messages(register_dict))


def test_a_real_observation_url_is_accepted(register_dict):
    register_dict["concepts"][0]["observations"][0]["url"] = "http://www.yso.fi/onto/yso/p6463"
    assert messages(register_dict) == []
