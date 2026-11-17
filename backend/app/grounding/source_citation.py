"""Deterministic source citations for retrieved documents (#114, PRD §7.3).

Every RAG answer's sources are built here from retrieval metadata, not composed
by the model, so a missing citation always means retrieval found nothing
citable and never that the model forgot to format one. Each source page is
cited once, in retrieval order, in one fixed format.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.grounding.citation_gate import canonical_url

SNIPPET_LENGTH = 280
NO_SOURCE_MESSAGE = (
    "I couldn't find a reliable official source for this question, so I won't guess at an answer. "
    "Please check with the relevant Finnish authority, such as Migri, Kela, or your municipality, "
    "or try rephrasing your question."
)


@dataclass(frozen=True)
class SourceCitation:
    """One official source page backing an answer."""

    title: str
    url: str
    snippet: str
    crawl_date: str | None = None

    @property
    def formatted(self) -> str:
        """The fixed citation string: ``Title — URL``, plus ``(retrieved DATE)`` when known."""
        text = f"{self.title} — {self.url}"
        return f"{text} (retrieved {self.crawl_date})" if self.crawl_date else text


def _source_url(metadata: dict[str, Any]) -> str | None:
    for key in ("citation_url", "source_url", "url"):
        value = metadata.get(key)
        if isinstance(value, str) and urlsplit(value.strip()).scheme in {"http", "https"}:
            return value.strip()
    return None


def _title(metadata: dict[str, Any], url: str) -> str:
    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        return " ".join(title.split())
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path.rstrip('/')}"


def format_citations(documents: Iterable[Any]) -> list[SourceCitation]:
    """Turn retrieved documents into one citation per source page.

    A document without an http(s) URL can't be verified by the user, so it is
    not cited. When several chunks come from the same page, the first one's
    title and snippet are kept.

    Args:
        documents: Retrieved documents, in retrieval order, each with ``metadata``
            and ``page_content``.

    Returns:
        The citations, in retrieval order. Empty means no citable source was found.
    """
    citations: list[SourceCitation] = []
    seen: set[str] = set()
    for document in documents:
        metadata = getattr(document, "metadata", None) or {}
        url = _source_url(metadata)
        if url is None or canonical_url(url) in seen:
            continue
        seen.add(canonical_url(url))
        content = getattr(document, "page_content", "") or ""
        crawl_date = metadata.get("crawl_date")
        citations.append(
            SourceCitation(
                title=_title(metadata, url),
                url=url,
                snippet=content[:SNIPPET_LENGTH],
                crawl_date=str(crawl_date) if crawl_date else None,
            )
        )
    return citations
