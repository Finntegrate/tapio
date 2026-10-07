"""Deterministic citation gate (#151, spec gate G2).

Every claim in a guide answer must cite chunk ids that were retrieved for that
turn. This module checks that without a model call. A citation given as a URL
that matches a retrieved chunk's source page is repaired to that chunk's id;
anything else that is not in the retrieved set is a failure, reported in a
form a targeted repair prompt can use.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk retrieved for this turn, with the page it came from."""

    chunk_id: str
    source_url: str


@dataclass(frozen=True)
class Claim:
    """One claim in an answer and the chunk ids it cites."""

    text: str
    cites: tuple[str, ...]


@dataclass(frozen=True)
class CitationRepair:
    """A near-miss citation rewritten to the retrieved chunk id it points at."""

    claim_index: int
    original: str
    repaired: str


@dataclass(frozen=True)
class CitationFailure:
    """A claim the gate rejected, with the citation that caused it."""

    claim_index: int
    claim_text: str
    failing_citation: str | None
    reason: str


@dataclass(frozen=True)
class CitationReport:
    """Outcome of the gate: repaired claims, repairs made, and any failures."""

    claims: tuple[Claim, ...]
    repairs: tuple[CitationRepair, ...] = field(default=())
    failures: tuple[CitationFailure, ...] = field(default=())

    @property
    def passed(self) -> bool:
        """True when no claim was rejected."""
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report for logging or a repair prompt."""
        return {
            "passed": self.passed,
            "repairs": [asdict(repair) for repair in self.repairs],
            "failures": [asdict(failure) for failure in self.failures],
        }


def _canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def check_citations(claims: Iterable[Claim], retrieved: Iterable[RetrievedChunk]) -> CitationReport:
    """Check every claim's citations against this turn's retrieved chunks.

    Args:
        claims: The claims in the answer, each with the chunk ids it cites.
        retrieved: The chunks retrieved for this turn.

    Returns:
        The claims with near-miss citations repaired, the repairs made, and one
        failure per claim that still has an invalid or missing citation.
    """
    chunks = list(retrieved)
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    id_by_url = {_canonical_url(chunk.source_url): chunk.chunk_id for chunk in chunks}

    repaired_claims: list[Claim] = []
    repairs: list[CitationRepair] = []
    failures: list[CitationFailure] = []

    for index, claim in enumerate(claims):
        if not claim.cites:
            failures.append(CitationFailure(index, claim.text, None, "no_citations"))
            repaired_claims.append(claim)
            continue

        new_cites: list[str] = []
        claim_repairs: list[CitationRepair] = []
        rejected = False
        for citation in claim.cites:
            if citation in chunk_ids:
                new_cites.append(citation)
                continue
            near_miss = id_by_url.get(_canonical_url(citation))
            if near_miss is not None:
                claim_repairs.append(CitationRepair(index, citation, near_miss))
                new_cites.append(near_miss)
                continue
            failures.append(CitationFailure(index, claim.text, citation, "not_retrieved"))
            rejected = True
            break

        # A claim's repairs only take effect if the whole claim is accepted — a repair
        # recorded for a claim that still ends up rejected would contradict the claim's
        # unchanged `cites`, since a rejected claim keeps its original form below.
        if rejected:
            repaired_claims.append(claim)
        else:
            repairs.extend(claim_repairs)
            repaired_claims.append(Claim(text=claim.text, cites=tuple(new_cites)))

    return CitationReport(
        claims=tuple(repaired_claims),
        repairs=tuple(repairs),
        failures=tuple(failures),
    )
