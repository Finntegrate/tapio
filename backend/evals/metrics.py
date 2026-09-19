"""Pure scoring helpers for retrieval evaluation."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

_URL_KEYS = ("citation_url", "source_url", "url")


def normalize_url(url: str) -> str:
    """Reduce a URL to a comparable form (no fragment, no trailing slash, lower case)."""
    return url.strip().split("#", maxsplit=1)[0].rstrip("/").lower()


def retrieved_urls(documents: Iterable[Any]) -> list[str]:
    """Extract the source URL of each retrieved document, in retrieval order.

    Documents without any URL metadata yield an empty string so that ranks
    stay aligned with the retrieval order.
    """
    urls: list[str] = []
    for document in documents:
        metadata = getattr(document, "metadata", None) or {}
        urls.append(next((normalize_url(metadata[key]) for key in _URL_KEYS if metadata.get(key)), ""))
    return urls


def first_hit_rank(retrieved: Sequence[str], expected: Iterable[str]) -> int | None:
    """Return the 1-based rank of the first retrieved URL that is expected, else None."""
    wanted = {normalize_url(url) for url in expected}
    for rank, url in enumerate(retrieved, start=1):
        if url in wanted:
            return rank
    return None


@dataclass(frozen=True)
class RetrievalSummary:
    """Aggregate retrieval quality over a set of questions.

    Attributes:
        cases: Number of questions scored.
        hit_rate: Share of questions whose expected page appeared in the top results.
        mrr: Mean reciprocal rank; 1.0 means the expected page was always first.
    """

    cases: int
    hit_rate: float
    mrr: float


def summarize_ranks(ranks: Sequence[int | None]) -> RetrievalSummary:
    """Aggregate per-question first-hit ranks into hit rate and MRR."""
    if not ranks:
        return RetrievalSummary(cases=0, hit_rate=0.0, mrr=0.0)
    hits = [rank for rank in ranks if rank is not None]
    return RetrievalSummary(
        cases=len(ranks),
        hit_rate=len(hits) / len(ranks),
        mrr=sum(1 / rank for rank in hits) / len(ranks),
    )
