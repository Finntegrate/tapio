"""Measure the current guardrail checks against evals/guardrail_decisions.yaml.

This is the baseline a decision-model backend has to beat: the production
``LLMGuardrailClassifier`` checks (one structured-output chat call each) and the
guardrail intro's contact-detail regex, run on the same labelled set.

Each check runs on its own, one call at a time, so latency is per call rather
than blurred by the three checks sharing one local Ollama. A check that fails
for infra or parse reasons is counted separately, not silently as "no match"
the way the classifier's fail-open policy would.

Usage (from backend/):
    python -m evals.run_guardrail_baseline --model gemma3:4b
    python -m evals.run_guardrail_baseline --model gemma3:4b --limit 5   # smoke run
"""

# ruff: noqa: T201, SLF001
# A CLI that prints its progress, and runs the classifier's own checks one at a time
# (its private _run_check/_structured_model) so the baseline is exactly production's.

import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.config.config_models import RAGConfig
from app.config.llm_settings import GUARDRAIL_ROLE, LLMSettings
from app.guardrails import LLMGuardrailClassifier
from app.guardrails.llm_classifier import _CHECKS
from app.guardrails.responses import _CONTACT_DETAIL_PATTERNS
from app.services.chat_model import build_chat_model
from app.services.structured_output import StructuredOutputFailure, StructuredOutputResult

EVALS_DIR = Path(__file__).parent
DATASET = EVALS_DIR / "guardrail_decisions.yaml"
# statistics.quantiles needs enough samples for a p95 to mean anything.
MIN_SAMPLES_FOR_P95 = 20
RESULTS_DIR = EVALS_DIR / "results"


@dataclass
class Outcome:
    """One check's verdict on one item."""

    item_id: str
    check: str
    difficulty: str
    language: str
    expected: bool
    predicted: bool | None  # None when the call failed (infra or parse)
    failure: str | None
    latency_s: float


@dataclass
class CheckSummary:
    """Confusion counts and rates for one check."""

    check: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    failed: int = 0
    misses: list[str] = field(default_factory=list)
    false_alarms: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float | None:
        """Share of expected matches the check caught, or None with no positives."""
        positives = self.tp + self.fn
        return self.tp / positives if positives else None

    @property
    def false_positive_rate(self) -> float | None:
        """Share of expected non-matches the check flagged, or None with no negatives."""
        negatives = self.fp + self.tn
        return self.fp / negatives if negatives else None


def summarize(outcomes: list[Outcome]) -> dict[str, CheckSummary]:
    """Group outcomes into per-check confusion counts, scored by the verdict production acts on.

    A failed call is counted in ``failed`` whatever its verdict: an infra failure fails open
    (no match), while a repeated parse failure on the crisis check escalates to a match, so
    counting only missing verdicts would hide those behind a perfect recall.
    """
    summaries: dict[str, CheckSummary] = {}
    for outcome in outcomes:
        summary = summaries.setdefault(outcome.check, CheckSummary(outcome.check))
        if outcome.failure is not None:
            summary.failed += 1
        # Fail-open is what production does with a failed check, so score it that way.
        predicted = bool(outcome.predicted)
        if outcome.expected and predicted:
            summary.tp += 1
        elif outcome.expected:
            summary.fn += 1
            summary.misses.append(outcome.item_id)
        elif predicted:
            summary.fp += 1
            summary.false_alarms.append(outcome.item_id)
        else:
            summary.tn += 1
    return summaries


async def run_guardrail_checks(classifier: LLMGuardrailClassifier, messages: list[dict[str, Any]]) -> list[Outcome]:
    """Run every guardrail check on every message, one call at a time."""
    structured = classifier._structured_model
    real_ainvoke = structured.ainvoke
    last_result: list[StructuredOutputResult[Any]] = []

    async def recording_ainvoke(prompt: Any) -> StructuredOutputResult[Any]:
        result = await real_ainvoke(prompt)
        last_result.append(result)
        return result

    structured.ainvoke = recording_ainvoke  # type: ignore[method-assign]

    outcomes = []
    for index, item in enumerate(messages, start=1):
        for check in _CHECKS:
            last_result.clear()
            started = time.perf_counter()
            match = await classifier._run_check(check, item["text"])
            latency = time.perf_counter() - started
            failure = last_result[-1].failure if last_result else None
            # A parse failure on the crisis check escalates to a match by policy; record the
            # failure either way, but keep the verdict production would act on.
            failed = failure is StructuredOutputFailure.INFRA or (failure is not None and match is None)
            outcomes.append(
                Outcome(
                    item_id=item["id"],
                    check=check.category.value,
                    difficulty=item["difficulty"],
                    language=item["language"],
                    expected=check.category.value in item["expect"],
                    predicted=None if failed else match is not None,
                    failure=failure.value if failure else None,
                    latency_s=round(latency, 3),
                )
            )
        print(f"  [{index}/{len(messages)}] {item['id']}", flush=True)
    return outcomes


def run_contact_regex(intros: list[dict[str, Any]]) -> list[Outcome]:
    """Run the production contact-detail regex on every intro."""
    return [
        Outcome(
            item_id=item["id"],
            check="contact_detail",
            difficulty=item["difficulty"],
            language=item["language"],
            expected=bool(item["expect"]),
            predicted=any(pattern.search(item["text"]) for pattern in _CONTACT_DETAIL_PATTERNS),
            failure=None,
            latency_s=0.0,  # microseconds; not worth reporting next to model calls
        )
        for item in intros
    ]


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def render_report(model: str, outcomes: list[Outcome]) -> str:
    """Render a Markdown summary: per-check rates, latency, and which items were wrong."""
    summaries = summarize(outcomes)
    lines = [
        f"### Baseline: structured-output `{model}` + contact-detail regex",
        "",
        "| Check | Recall | False-positive rate | Failed calls | Misses | False alarms |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {summary.check} | {_pct(summary.recall)} ({summary.tp}/{summary.tp + summary.fn}) "
        f"| {_pct(summary.false_positive_rate)} ({summary.fp}/{summary.fp + summary.tn}) "
        f"| {summary.failed} | {', '.join(summary.misses) or '-'} | {', '.join(summary.false_alarms) or '-'} |"
        for summary in summaries.values()
    )

    llm_latencies = [o.latency_s for o in outcomes if o.check != "contact_detail"]
    if llm_latencies:
        median = statistics.median(llm_latencies)
        p95 = (
            statistics.quantiles(llm_latencies, n=20)[-1]
            if len(llm_latencies) >= MIN_SAMPLES_FOR_P95
            else max(llm_latencies)
        )
        lines += [
            "",
            (
                f"Latency per guardrail check: median {median:.1f}s, p95 {p95:.1f}s. "
                f"A turn runs {len(_CHECKS)} checks, so a turn on one local Ollama costs roughly "
                f"{median * len(_CHECKS):.0f}s when they serialize. Cost per turn: $0 (local compute)."
            ),
        ]

    by_difficulty: dict[str, list[Outcome]] = defaultdict(list)
    for outcome in outcomes:
        by_difficulty[outcome.difficulty].append(outcome)
    lines += ["", "| Difficulty | Correct |", "| --- | --- |"]
    for difficulty, group in sorted(by_difficulty.items()):
        correct = sum(bool(o.predicted) == o.expected for o in group)
        lines.append(f"| {difficulty} | {correct}/{len(group)} |")

    lines += [
        "",
        (
            "Calibration: not measurable. The structured-output path returns a bare boolean, so there is "
            "no score to set a threshold on; recall is reported at its single operating point."
        ),
    ]
    return "\n".join(lines)


async def main() -> None:
    """Run the baseline on the labelled set and write JSON and Markdown results."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", required=True, help="Ollama model tag, e.g. gemma3:4b")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N messages (smoke run)")
    args = parser.parse_args()

    dataset = yaml.safe_load(DATASET.read_text(encoding="utf-8"))
    messages = dataset["messages"][: args.limit]

    config = replace(RAGConfig(), llm_provider="ollama", llm_model_name=args.model, llm_model_overrides={})
    classifier = LLMGuardrailClassifier(build_chat_model(config, LLMSettings(), role=GUARDRAIL_ROLE))

    # Load the model before timing anything; a cold Ollama load can exceed the check timeout.
    await classifier._run_check(_CHECKS[0], "warm-up")

    print(f"Running {len(messages)} messages x {len(_CHECKS)} checks on {args.model}", flush=True)
    outcomes = await run_guardrail_checks(classifier, messages)
    outcomes += run_contact_regex(dataset["intros"])

    report = render_report(args.model, outcomes)
    print("\n" + report)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = args.model.replace(":", "-").replace("/", "-")
    (RESULTS_DIR / f"{stamp}-{slug}.json").write_text(
        json.dumps({"model": args.model, "outcomes": [asdict(o) for o in outcomes]}, indent=2), encoding="utf-8"
    )
    (RESULTS_DIR / f"{stamp}-{slug}.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
