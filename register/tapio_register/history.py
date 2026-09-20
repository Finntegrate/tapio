"""Reading the register as a record of how things changed.

Kept apart from :mod:`tapio_register.skos` because these answer questions about
the register rather than publish it, and because a consumer asking what was in
force in 2018 should not have to import an RDF library to find out.
"""

from datetime import date

from tapio_register.generated.term_register_model import Concept, TermRegister


def is_in_force(concept: Concept, reference: date) -> bool:
    """Say whether ``concept`` is in force on ``reference``.

    Both ends matter. A concept with a ``valid_until`` in the future has not
    lapsed, and one whose ``valid_from`` has not yet arrived is not in force
    however far off its end is. Both bounds are inclusive, so a body dissolved
    on 1 January was still in force on 31 December.
    """
    if concept.valid_from > reference:
        return False
    return concept.valid_until is None or concept.valid_until >= reference


def in_force_on(register: TermRegister, reference: date) -> list[Concept]:
    """Return the concepts in force on ``reference``.

    This is the time slice that lets a claim about the past be read against the
    state of affairs at its own date rather than against today.
    """
    return [concept for concept in register.concepts if is_in_force(concept, reference)]


def lineage(register: TermRegister, concept_id: str) -> list[Concept]:
    """Follow supersession forward, from a concept to what stands in its place.

    A source written in 2018 names a body that has since been dissolved twice
    over. Someone who had worked at the agency for years would remember that
    and say what it is called now; this is that recollection, made explicit.

    The first element is the concept asked about and the last is the one in
    force, so a caller can render the whole chain or only its end. A concept
    that never lapsed is a chain of one.
    """
    known = {concept.id: concept for concept in register.concepts}
    chain: list[Concept] = []
    seen: set[str] = set()
    current: str | None = concept_id
    while current is not None and current in known and current not in seen:
        seen.add(current)
        concept = known[current]
        chain.append(concept)
        # The chain stops at a branch. A concept whose work was split across
        # several bodies has no single "what it is now", and picking one would
        # make the answer depend on the order two ids happen to be written in.
        # The branch point itself is the honest end of the chain; a caller that
        # wants the branches reads them off its `superseded_by`.
        successors = concept.superseded_by or []
        current = successors[0] if len(successors) == 1 else None
    return chain
