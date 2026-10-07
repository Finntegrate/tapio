"""Tests for the deterministic citation gate (#151, spec gate G2)."""

import json

from app.grounding.citation_gate import Claim, RetrievedChunk, check_citations

RETRIEVED = [
    RetrievedChunk(chunk_id="chunk-kotikunta-1", source_url="https://migri.fi/kotikunta"),
    RetrievedChunk(chunk_id="chunk-ajanvaraus-1", source_url="https://migri.fi/ajanvaraus"),
]


def test_passes_when_every_claim_cites_a_retrieved_chunk() -> None:
    claims = [Claim(text="Kotikunta is your home municipality.", cites=("chunk-kotikunta-1",))]

    report = check_citations(claims, RETRIEVED)

    assert report.passed
    assert report.claims == tuple(claims)
    assert report.failures == ()
    assert report.repairs == ()


def test_rejects_a_claim_with_no_citations() -> None:
    claims = [Claim(text="Appointments are free.", cites=())]

    report = check_citations(claims, RETRIEVED)

    assert not report.passed
    assert len(report.failures) == 1
    assert report.failures[0].reason == "no_citations"
    assert report.failures[0].failing_citation is None


def test_rejects_a_citation_to_a_chunk_that_was_not_retrieved() -> None:
    claims = [Claim(text="Permits take 90 days.", cites=("chunk-invented-9",))]

    report = check_citations(claims, RETRIEVED)

    assert not report.passed
    assert report.failures[0].reason == "not_retrieved"
    assert report.failures[0].failing_citation == "chunk-invented-9"


def test_auto_repairs_a_url_that_maps_to_a_retrieved_chunk() -> None:
    claims = [Claim(text="Book via the booking service.", cites=("https://MIGRI.fi/ajanvaraus/",))]

    report = check_citations(claims, RETRIEVED)

    assert report.passed
    assert report.claims[0].cites == ("chunk-ajanvaraus-1",)
    assert len(report.repairs) == 1
    assert report.repairs[0].original == "https://MIGRI.fi/ajanvaraus/"
    assert report.repairs[0].repaired == "chunk-ajanvaraus-1"


def test_rejects_a_url_that_maps_to_no_retrieved_chunk() -> None:
    claims = [Claim(text="Something else.", cites=("https://migri.fi/never-retrieved",))]

    report = check_citations(claims, RETRIEVED)

    assert not report.passed
    assert report.failures[0].reason == "not_retrieved"


def test_mixed_claims_report_only_the_failing_ones_and_keep_repairs() -> None:
    claims = [
        Claim(text="Good claim.", cites=("chunk-kotikunta-1",)),
        Claim(text="Repairable claim.", cites=("https://migri.fi/ajanvaraus",)),
        Claim(text="Bad claim.", cites=("chunk-invented-9",)),
    ]

    report = check_citations(claims, RETRIEVED)

    assert not report.passed
    assert [failure.claim_index for failure in report.failures] == [2]
    assert report.claims[1].cites == ("chunk-ajanvaraus-1",)
    assert len(report.repairs) == 1


def test_empty_retrieval_set_rejects_every_citation() -> None:
    claims = [Claim(text="Anything.", cites=("chunk-kotikunta-1",))]

    report = check_citations(claims, retrieved=[])

    assert not report.passed
    assert report.failures[0].reason == "not_retrieved"


def test_failure_report_is_machine_readable_for_a_repair_prompt() -> None:
    claims = [Claim(text="Bad claim.", cites=("chunk-invented-9",))]

    report = check_citations(claims, RETRIEVED)

    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["passed"] is False
    assert payload["failures"] == [
        {
            "claim_index": 0,
            "claim_text": "Bad claim.",
            "failing_citation": "chunk-invented-9",
            "reason": "not_retrieved",
        }
    ]
