"""Tests for the deterministic source-citation formatter (#114)."""

from types import SimpleNamespace

from app.grounding import SourceCitation, format_citations


def _doc(content: str = "Some text.", **metadata: object) -> SimpleNamespace:
    return SimpleNamespace(page_content=content, metadata=metadata)


def test_a_citation_has_one_fixed_format() -> None:
    (citation,) = format_citations([_doc(title="Residence permits", source_url="https://migri.fi/en/permits")])

    assert citation.formatted == "Residence permits — https://migri.fi/en/permits"


def test_the_crawl_date_is_added_when_known() -> None:
    (citation,) = format_citations([_doc(title="Kela", source_url="https://kela.fi", crawl_date="2026-11-01")])

    assert citation.formatted == "Kela — https://kela.fi (retrieved 2026-11-01)"


def test_chunks_from_the_same_page_are_cited_once_in_retrieval_order() -> None:
    citations = format_citations(
        [
            _doc("first", title="A", source_url="https://migri.fi/a"),
            _doc(title="B", source_url="https://kela.fi/b"),
            _doc("second", title="A again", source_url="HTTPS://MIGRI.FI/a/#section"),
        ]
    )

    assert [c.url for c in citations] == ["https://migri.fi/a", "https://kela.fi/b"]
    assert citations[0].title == "A"
    assert citations[0].snippet == "first"


def test_the_url_comes_from_citation_url_then_source_url_then_url() -> None:
    (citation,) = format_citations(
        [_doc(citation_url="https://a.fi", source_url="https://b.fi", url="https://c.fi", title="T")]
    )

    assert citation.url == "https://a.fi"


def test_a_document_without_a_web_url_is_not_cited() -> None:
    citations = format_citations(
        [
            _doc(title="Local file", url="archive/crawled/example.com/page.html"),
            _doc(title="No url"),
            SimpleNamespace(page_content="no metadata at all"),
        ]
    )

    assert citations == []


def test_a_malformed_url_is_skipped_without_losing_the_other_citations() -> None:
    citations = format_citations(
        [
            _doc(title="Broken", source_url="https://[migri.fi"),
            _doc(title="Fine", source_url="https://kela.fi"),
        ]
    )

    assert [c.title for c in citations] == ["Fine"]


def test_a_malformed_url_falls_through_to_the_next_metadata_key() -> None:
    (citation,) = format_citations([_doc(title="T", citation_url="https://[bad", source_url="https://migri.fi")])

    assert citation.url == "https://migri.fi"


def test_a_url_without_a_host_is_not_a_source() -> None:
    assert format_citations([_doc(source_url="https://"), _doc(source_url="https:///permits")]) == []


def test_a_missing_title_falls_back_to_the_page_address() -> None:
    (citation,) = format_citations([_doc(source_url="https://migri.fi/en/work/")])

    assert citation.title == "migri.fi/en/work"


def test_titles_are_whitespace_normalised_and_snippets_are_bounded() -> None:
    (citation,) = format_citations([_doc("x" * 1000, title="  Two\n  lines ", source_url="https://kela.fi")])

    assert citation.title == "Two lines"
    assert len(citation.snippet) == 280


def test_no_documents_means_no_citations() -> None:
    assert format_citations([]) == []


def test_formatted_omits_the_date_when_unknown() -> None:
    assert SourceCitation("T", "https://x.fi", "s").formatted == "T — https://x.fi"
