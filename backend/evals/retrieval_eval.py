"""Score how often retrieval returns the expected source page.

Run from ``backend/``::

    uv run python -m evals.retrieval_eval --k 5
    uv run python -m evals.retrieval_eval --collection other_chunks --output results.json

To compare chunk sizes, ingest the same content into one collection per
setting and run this once per ``--collection``. To compare embedding models,
pass ``--embedding-model`` (the collection must have been built with it).
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from evals.dataset import DEFAULT_GOLDEN_SET, GoldenCase, load_golden_set
from evals.metrics import RetrievalSummary, first_hit_rank, retrieved_urls, summarize_ranks

Retrieve = Callable[[str, int], list[Any]]


def _positive_int(raw: str) -> int:
    """Parse an ``argparse`` value, rejecting zero and negative integers."""
    value = int(raw)
    if value < 1:
        msg = f"must be a positive integer, got {value}"
        raise argparse.ArgumentTypeError(msg)
    return value


@dataclass(frozen=True)
class RetrievalCaseResult:
    """Outcome of retrieval for one golden question."""

    id: str
    rank: int | None
    retrieved_urls: list[str]


@dataclass(frozen=True)
class RetrievalReport:
    """Per-question results plus the aggregate summary."""

    summary: RetrievalSummary
    results: list[RetrievalCaseResult]


def evaluate_retrieval(retrieve: Retrieve, cases: Sequence[GoldenCase], k: int) -> RetrievalReport:
    """Run every golden question through retrieval and score the results.

    Args:
        retrieve: Function returning the top ``k`` documents for a query.
        cases: Golden questions to evaluate.
        k: How many documents to retrieve per question.

    Returns:
        The aggregate summary and the per-question results.
    """
    results: list[RetrievalCaseResult] = []
    for case in cases:
        urls = retrieved_urls(retrieve(case.question, k))
        results.append(
            RetrievalCaseResult(
                id=case.id,
                rank=first_hit_rank(urls, case.expected_source_urls),
                retrieved_urls=urls,
            )
        )
    return RetrievalReport(summary=summarize_ranks([result.rank for result in results]), results=results)


def format_report(report: RetrievalReport, k: int) -> str:
    """Render a report as a short plain-text table."""
    lines = [f"{'case':<28} {'first hit rank':<15}"]
    lines.extend(
        f"{result.id:<28} {result.rank if result.rank is not None else 'MISS':<15}" for result in report.results
    )
    summary = report.summary
    lines.append(f"\ncases={summary.cases}  hit@{k}={summary.hit_rate:.2f}  MRR={summary.mrr:.2f}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point; returns a process exit code."""
    from app.config.config_models import RAGConfig  # noqa: PLC0415
    from app.factories import RAGOrchestratorFactory  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Evaluate Tapio retrieval quality.")
    parser.add_argument("--golden-set", type=Path, default=DEFAULT_GOLDEN_SET)
    parser.add_argument("--k", type=_positive_int, default=5, help="documents retrieved per question")
    parser.add_argument("--collection", help="Chroma collection name")
    parser.add_argument("--persist-directory", help="Chroma directory")
    parser.add_argument("--embedding-model", help="embedding model the collection was built with")
    parser.add_argument("--output", type=Path, help="write the full report as JSON")
    args = parser.parse_args(argv)

    overrides = {
        "collection_name": args.collection,
        "persist_directory": args.persist_directory,
        "embedding_model_name": args.embedding_model,
    }
    config = RAGConfig(**{key: value for key, value in overrides.items() if value})
    retriever = RAGOrchestratorFactory(config).create_retriever()

    report = evaluate_retrieval(
        lambda query, n: retriever.query(query, n_results=n), load_golden_set(args.golden_set), args.k
    )
    sys.stdout.write(format_report(report, args.k) + "\n")
    if args.output:
        args.output.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
