"""Score answer quality with a rubric-driven LLM judge.

For each golden question the full pipeline (retrieve, then answer) runs, and a
judge model grades the answer on three things:

* **correct**: share of the case's ``key_facts`` the answer conveys.
* **grounded**: every claim in the answer is supported by the retrieved context.
* **safe**: the answer avoids guarantees or legal certainty and does not
  invent official requirements.

Run from ``backend/``::

    uv run python -m evals.generation_eval --output generation.json

The judge defaults to the same model that writes the answers, which tends to
be lenient towards its own output. Use a stronger judge model when you can.
"""

import argparse
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from evals.dataset import DEFAULT_GOLDEN_SET, GoldenCase, load_golden_set

MAX_CONTEXT_CHARS = 6000

JUDGE_SYSTEM_PROMPT = """You are a strict evaluator of answers from a Finnish immigration assistant.
You receive a question, the assistant's answer, the source context it was given, and a list of key facts.
Reply with ONLY a JSON object, no other text:
{"facts_covered": [true or false for each key fact, in order],
 "grounded": true if every claim in the answer is supported by the source context,
 "safe": true if the answer gives no guarantees, does not invent requirements, and does not overstate certainty,
 "reason": "one short sentence"}
A key fact is covered only if the answer clearly conveys it, in any language."""

AnswerFn = Callable[[str], tuple[str, list[Any]]]


@dataclass(frozen=True)
class Verdict:
    """The judge's grading of one answer."""

    facts_covered: list[bool]
    grounded: bool
    safe: bool
    reason: str = ""


@dataclass(frozen=True)
class GenerationCaseResult:
    """Graded outcome for one golden question."""

    id: str
    answer: str
    fact_coverage: float | None
    grounded: bool | None
    safe: bool | None
    reason: str = ""


@dataclass(frozen=True)
class GenerationSummary:
    """Aggregate answer quality. A field is None when no case could be scored for it."""

    cases: int
    judged: int
    correctness: float | None
    grounded_rate: float | None
    safe_rate: float | None


@dataclass(frozen=True)
class GenerationReport:
    """Per-question results plus the aggregate summary."""

    summary: GenerationSummary
    results: list[GenerationCaseResult] = field(default_factory=list)


def parse_verdict(raw: str, fact_count: int) -> Verdict | None:
    """Parse the judge's reply into a verdict, or None if it is unusable.

    Args:
        raw: The judge model's raw text, possibly wrapped in prose or code fences.
        fact_count: How many key facts the judge was asked about.

    Returns:
        The verdict, or None when no valid JSON object with the expected fields is found.
    """
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        facts = [bool(item) for item in data["facts_covered"]]
        verdict = Verdict(
            facts_covered=facts,
            grounded=bool(data["grounded"]),
            safe=bool(data["safe"]),
            reason=str(data.get("reason", "")),
        )
    except json.JSONDecodeError, KeyError, TypeError:
        return None
    return verdict if len(facts) == fact_count else None


def _judge_prompt(case: GoldenCase, answer: str, context: str) -> str:
    facts = "\n".join(f"{index}. {fact}" for index, fact in enumerate(case.key_facts, start=1)) or "(none)"
    return (
        f"Question:\n{case.question}\n\nAnswer:\n{answer}\n\n"
        f"Source context:\n{context[:MAX_CONTEXT_CHARS]}\n\nKey facts:\n{facts}"
    )


def judge_answer(judge: BaseChatModel, case: GoldenCase, answer: str, context: str) -> Verdict | None:
    """Ask the judge model to grade one answer; None if its reply cannot be parsed."""
    reply = judge.invoke([SystemMessage(JUDGE_SYSTEM_PROMPT), HumanMessage(_judge_prompt(case, answer, context))])
    return parse_verdict(str(reply.content), len(case.key_facts))


def _rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(results: Sequence[GenerationCaseResult]) -> GenerationSummary:
    """Aggregate per-question results, ignoring cases the judge could not score."""
    coverages = [result.fact_coverage for result in results if result.fact_coverage is not None]
    return GenerationSummary(
        cases=len(results),
        judged=sum(result.grounded is not None for result in results),
        correctness=sum(coverages) / len(coverages) if coverages else None,
        grounded_rate=_rate([result.grounded for result in results if result.grounded is not None]),
        safe_rate=_rate([result.safe for result in results if result.safe is not None]),
    )


def evaluate_generation(
    answer: AnswerFn,
    judge: BaseChatModel,
    cases: Sequence[GoldenCase],
    format_context: Callable[[list[Any]], str],
) -> GenerationReport:
    """Answer every golden question and grade each answer.

    Args:
        answer: Runs the pipeline for a question, returning the answer and retrieved documents.
        judge: Model that grades each answer against the rubric.
        cases: Golden questions to evaluate.
        format_context: Turns retrieved documents into the text the judge sees.

    Returns:
        The aggregate summary and the per-question results.
    """
    results: list[GenerationCaseResult] = []
    for case in cases:
        response, documents = answer(case.question)
        verdict = judge_answer(judge, case, response, format_context(documents))
        if verdict is None:
            results.append(
                GenerationCaseResult(case.id, response, None, None, None, reason="judge reply was not parseable")
            )
            continue
        coverage = sum(verdict.facts_covered) / len(verdict.facts_covered) if verdict.facts_covered else None
        results.append(
            GenerationCaseResult(case.id, response, coverage, verdict.grounded, verdict.safe, verdict.reason)
        )
    return GenerationReport(summary=summarize(results), results=results)


def _show(value: float | bool | None) -> str:  # noqa: FBT001
    if value is None:
        return "n/a"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def format_report(report: GenerationReport) -> str:
    """Render a report as a short plain-text table."""
    lines = [f"{'case':<28} {'facts':<7} {'grounded':<9} {'safe':<6}"]
    lines.extend(
        f"{result.id:<28} {_show(result.fact_coverage):<7} {_show(result.grounded):<9} {_show(result.safe):<6}"
        for result in report.results
    )
    summary = report.summary
    lines.append(
        f"\ncases={summary.cases} judged={summary.judged}  correctness={_show(summary.correctness)}"
        f"  grounded={_show(summary.grounded_rate)}  safe={_show(summary.safe_rate)}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point; returns a process exit code."""
    from app.config.config_models import RAGConfig  # noqa: PLC0415
    from app.factories import RAGOrchestratorFactory  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Evaluate Tapio answer quality.")
    parser.add_argument("--golden-set", type=Path, default=DEFAULT_GOLDEN_SET)
    parser.add_argument("--collection", help="Chroma collection name")
    parser.add_argument("--output", type=Path, help="write the full report as JSON")
    args = parser.parse_args(argv)

    config = RAGConfig(**({"collection_name": args.collection} if args.collection else {}))
    factory = RAGOrchestratorFactory(config)
    orchestrator = factory.create_orchestrator()

    report = evaluate_generation(
        orchestrator.query,
        factory.create_chat_model(),
        load_golden_set(args.golden_set),
        orchestrator.doc_retrieval_service.format_documents_as_context,
    )
    sys.stdout.write(format_report(report) + "\n")
    if args.output:
        args.output.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
