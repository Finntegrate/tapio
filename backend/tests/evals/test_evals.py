"""Tests for the offline retrieval and generation evaluation harness."""

from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from evals.dataset import DEFAULT_GOLDEN_SET, GoldenCase, load_golden_set
from evals.generation_eval import evaluate_generation, parse_verdict
from evals.metrics import first_hit_rank, normalize_url, retrieved_urls, summarize_ranks
from evals.retrieval_eval import evaluate_retrieval, format_report


def _doc(url: str | None) -> SimpleNamespace:
    return SimpleNamespace(page_content="text", metadata={"source_url": url} if url else {})


def _case(case_id: str = "c1", facts: tuple[str, ...] = ()) -> GoldenCase:
    return GoldenCase(case_id, "question?", "en", ("https://migri.fi/page",), facts)


class TestMetrics:
    def test_normalize_url_ignores_case_slash_and_fragment(self) -> None:
        assert normalize_url(" https://Migri.fi/Page/#top ") == "https://migri.fi/page"

    def test_retrieved_urls_prefers_citation_url_and_keeps_alignment(self) -> None:
        docs = [
            SimpleNamespace(metadata={"citation_url": "https://a.fi/", "source_url": "https://b.fi"}),
            _doc(None),
            _doc("https://c.fi"),
        ]

        assert retrieved_urls(docs) == ["https://a.fi", "", "https://c.fi"]

    def test_first_hit_rank_is_one_based(self) -> None:
        assert first_hit_rank(["x", "https://a.fi", "y"], ["https://A.fi/"]) == 2

    def test_first_hit_rank_is_none_on_miss(self) -> None:
        assert first_hit_rank(["x", "y"], ["https://a.fi"]) is None

    def test_summarize_ranks_computes_hit_rate_and_mrr(self) -> None:
        summary = summarize_ranks([1, 2, None, None])

        assert summary.cases == 4
        assert summary.hit_rate == 0.5
        assert summary.mrr == pytest.approx((1 + 0.5) / 4)

    def test_summarize_ranks_handles_no_cases(self) -> None:
        assert summarize_ranks([]).cases == 0


class TestDataset:
    def test_shipped_golden_set_loads_with_unique_ids(self) -> None:
        cases = load_golden_set(DEFAULT_GOLDEN_SET)

        assert len(cases) > 0
        assert len({case.id for case in cases}) == len(cases)
        assert all(case.expected_source_urls for case in cases)

    def test_missing_field_is_rejected(self, tmp_path) -> None:
        path = tmp_path / "bad.jsonl"
        path.write_text('{"id": "a", "question": "q"}\n', encoding="utf-8")

        with pytest.raises(ValueError, match="missing fields"):
            load_golden_set(path)

    def test_repeated_id_is_rejected(self, tmp_path) -> None:
        line = '{"id": "a", "question": "q", "language": "en", "expected_source_urls": ["u"]}\n'
        path = tmp_path / "dup.jsonl"
        path.write_text(line * 2, encoding="utf-8")

        with pytest.raises(ValueError, match="repeats id"):
            load_golden_set(path)


class TestRetrievalEval:
    def test_scores_hits_and_misses(self) -> None:
        cases = [_case("hit"), _case("miss")]
        results = {
            "hit": [_doc("https://other.fi"), _doc("https://migri.fi/page")],
            "miss": [_doc("https://other.fi")],
        }
        calls = iter(["hit", "miss"])

        report = evaluate_retrieval(lambda _query, _k: results[next(calls)], cases, k=5)

        assert [result.rank for result in report.results] == [2, None]
        assert report.summary.hit_rate == 0.5
        assert "MISS" in format_report(report, k=5)


class TestGenerationEval:
    def test_parse_verdict_accepts_fenced_json(self) -> None:
        raw = '```json\n{"facts_covered": [true, false], "grounded": true, "safe": true, "reason": "ok"}\n```'

        verdict = parse_verdict(raw, fact_count=2)

        assert verdict is not None
        assert verdict.facts_covered == [True, False]

    def test_parse_verdict_rejects_wrong_fact_count(self) -> None:
        raw = '{"facts_covered": [true], "grounded": true, "safe": true}'

        assert parse_verdict(raw, fact_count=2) is None

    @pytest.mark.parametrize("raw", ["no json here", '{"grounded": true}', "{not json}"])
    def test_parse_verdict_rejects_unusable_replies(self, raw: str) -> None:
        assert parse_verdict(raw, fact_count=0) is None

    def test_evaluate_generation_aggregates_judge_verdicts(self) -> None:
        judge = FakeListChatModel(
            responses=[
                '{"facts_covered": [true, false], "grounded": true, "safe": true, "reason": "half"}',
                "garbage",
            ]
        )
        cases = [_case("a", facts=("f1", "f2")), _case("b", facts=("f1", "f2"))]

        report = evaluate_generation(lambda _q: ("an answer", [_doc("u")]), judge, cases, lambda _docs: "context")

        assert report.results[0].fact_coverage == 0.5
        assert report.results[1].grounded is None
        assert report.summary.judged == 1
        assert report.summary.correctness == 0.5
        assert report.summary.grounded_rate == 1.0

    def test_case_without_key_facts_still_gets_grounded_and_safe_scores(self) -> None:
        judge = FakeListChatModel(responses=['{"facts_covered": [], "grounded": false, "safe": true}'])

        report = evaluate_generation(lambda _q: ("answer", []), judge, [_case()], lambda _docs: "")

        assert report.results[0].fact_coverage is None
        assert report.summary.correctness is None
        assert report.summary.grounded_rate == 0.0
        assert report.summary.safe_rate == 1.0
