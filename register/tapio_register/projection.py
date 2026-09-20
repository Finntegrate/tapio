"""Render the register into the two shapes a model actually consumes.

The register as curated is a concept per entity with its own provenance, which
is the right shape for a person maintaining it and the wrong shape for a prompt.
Two projections come out of it:

*Options* are what a classifier picks from — one line per concept, scoped to
the guide that will answer. *Facts* are what the answering guide generates
against — the handful of concepts a turn is actually about, with the things it
needs to be exact about: what they are called in each language, who handles
them, whether they are still in force, and what replaced them if not.

Deliberately free of the authoring toolchain, so a consumer ships the data and
this module and nothing else.
"""

from datetime import date
from typing import Any

from tapio_register import history
from tapio_register.generated.term_register_model import Concept, TermRegister
from tapio_register.loading import concepts_by_id, enum_value


def _labels(concept: Concept) -> str:
    return f"{concept.pref_label.en} / {concept.pref_label.fi} / {concept.pref_label.sv}"


def options(
    register: TermRegister,
    guide: str | None = None,
    kinds: list[str] | None = None,
    *,
    include_lapsed: bool = True,
    reference: date | None = None,
) -> dict[str, str]:
    """Return ``concept id -> label``, the set a classifier chooses from.

    Scoped to one guide, the set is small enough to put in front of a model as
    a list to pick from rather than a name to recall. Concepts out of force are
    kept by default and marked: a person asking about the TE Office should have
    that recognised, and then be told what replaced it, rather than not matched
    at all.

    A known end date is always shown, whether or not it has arrived. What
    ``include_lapsed`` decides is only whether concepts *not in force on*
    ``reference`` are offered at all — a body that closes next year is still a
    body to pick today.
    """
    on = reference or date.today()  # noqa: DTZ011 - validity is a calendar question
    chosen: dict[str, str] = {}
    for concept in register.concepts:
        if guide is not None and guide not in [enum_value(g) for g in concept.in_scope_of]:
            continue
        if kinds is not None and enum_value(concept.kind) not in kinds:
            continue
        if not history.is_in_force(concept, on) and not include_lapsed:
            continue
        chosen[concept.id] = _labels(concept)
        if concept.valid_until is not None:
            chosen[concept.id] += f" (until {concept.valid_until})"
        elif concept.valid_from > on:
            chosen[concept.id] += f" (from {concept.valid_from})"
    return chosen


def facts(
    register: TermRegister,
    concept_ids: list[str],
    reference: date | None = None,
) -> list[dict[str, Any]]:
    """Return what a guide needs to be exact about, for the concepts of one turn.

    Only the concepts a turn concerns, so this stays short enough to put in a
    prompt whatever the register grows to. A lapsed concept carries what
    replaced it, because the useful answer to "where is my TE Office" names the
    body that took over rather than refusing the question.
    """
    known = concepts_by_id(register)
    on = reference or date.today()  # noqa: DTZ011 - validity is a calendar question
    rendered: list[dict[str, Any]] = []
    for concept_id in concept_ids:
        concept = known.get(concept_id)
        if concept is None:
            continue
        fact: dict[str, Any] = {
            "id": concept.id,
            "kind": enum_value(concept.kind),
            "labels": {"en": concept.pref_label.en, "fi": concept.pref_label.fi, "sv": concept.pref_label.sv},
            "in_force": history.is_in_force(concept, on),
        }
        if concept.definition is not None and concept.definition.en:
            fact["definition"] = concept.definition.en
        handled_by = [known[a].pref_label.en for a in concept.handled_by or [] if a in known]
        if handled_by:
            fact["handled_by"] = handled_by
        if concept.valid_from > on:
            # Not in force because it has not started yet, which is a different
            # thing from having lapsed and must not be reported as supersession.
            fact["in_force_from"] = concept.valid_from
        elif not fact["in_force"]:
            fact["lapsed_on"] = concept.valid_until
            chain = history.lineage(register, concept.id)[1:]
            if chain:
                fact["replaced_by"] = [{"id": c.id, "label": c.pref_label.en} for c in chain]
            if concept.change_note:
                fact["what_changed"] = concept.change_note
        rendered.append(fact)
    return rendered


def as_prompt_block(rendered: list[dict[str, Any]]) -> str:
    """Render facts as the plain text that goes in front of a guide.

    Plain lines rather than JSON: this is read by a model alongside prose, and
    the register's own structure is not the point at the moment of answering.
    """
    lines: list[str] = []
    for fact in rendered:
        labels = fact["labels"]
        lines.append(f"- {labels['en']} ({labels['fi']} / {labels['sv']}) [{fact['id']}]")
        if "definition" in fact:
            lines.append(f"    {fact['definition']}")
        if fact.get("handled_by"):
            lines.append(f"    Handled by: {', '.join(fact['handled_by'])}")
        if "in_force_from" in fact:
            lines.append(f"    Not in force until {fact['in_force_from']}.")
        elif not fact["in_force"]:
            replaced = ", ".join(r["label"] for r in fact.get("replaced_by", []))
            lines.append(
                f"    No longer in force since {fact['lapsed_on']}."
                + (f" Replaced by: {replaced}." if replaced else "")
            )
            if "what_changed" in fact:
                lines.append(f"    {fact['what_changed']}")
    return "\n".join(lines)
