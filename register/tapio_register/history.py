"""Reading the register as a record of how things changed.

Kept apart from :mod:`tapio_register.skos` because these answer questions about
the register rather than publish it, and because a consumer asking what was in
force in 2018 should not have to import an RDF library to find out.
"""

from datetime import date

from tapio_register.generated.term_register_model import Concept, TermRegister


def in_force_on(register: TermRegister, reference: date) -> list[Concept]:
    """Return the concepts in force on ``reference``.

    ``valid_until`` is inclusive, so an entity dissolved on 1 January is still
    in force on 31 December. This is the time slice that lets a claim about the
    past be checked against the state of affairs at its own date rather than
    against today.
    """
    return [
        concept
        for concept in register.concepts
        if concept.valid_from <= reference and (concept.valid_until is None or concept.valid_until >= reference)
    ]


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
        # Only the first successor is followed. A concept whose work was split
        # across several bodies has no single "what it is now", and inventing
        # one would be a worse answer than the branch point itself.
        successors = concept.superseded_by or []
        current = successors[0] if successors else None
    return chain
