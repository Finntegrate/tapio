"""Keep evals/guardrail_decisions.yaml well-formed and balanced enough to measure anything."""

from collections import Counter
from pathlib import Path

import pytest
import yaml

from app.guardrails.classifier import GuardrailCategory
from evals.run_guardrail_baseline import Outcome, summarize

DATASET = Path(__file__).parents[2] / "evals" / "guardrail_decisions.yaml"
CHECKS = {category.value for category in GuardrailCategory}
REQUIRED_KEYS = {"id", "text", "language", "difficulty", "expect", "why"}


@pytest.fixture(scope="module")
def dataset() -> dict:
    return yaml.safe_load(DATASET.read_text(encoding="utf-8"))


def test_every_item_has_the_required_keys(dataset: dict) -> None:
    for item in dataset["messages"] + dataset["intros"]:
        assert set(item) >= REQUIRED_KEYS, item.get("id")


def test_ids_are_unique(dataset: dict) -> None:
    ids = Counter(item["id"] for item in dataset["messages"] + dataset["intros"])
    assert [item_id for item_id, count in ids.items() if count > 1] == []


def test_message_labels_name_real_guardrail_checks(dataset: dict) -> None:
    for item in dataset["messages"]:
        assert set(item["expect"]) <= CHECKS, item["id"]


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_each_check_has_positives_negatives_and_non_english_cases(dataset: dict, check: str) -> None:
    positives = [item for item in dataset["messages"] if check in item["expect"]]
    negatives = [item for item in dataset["messages"] if check not in item["expect"]]
    assert len(positives) >= 5
    assert len(negatives) >= 5
    assert any(item["language"] != "en" for item in positives)


def test_intros_cover_both_labels_and_the_shapes_the_regex_misses(dataset: dict) -> None:
    labels = Counter(item["expect"] for item in dataset["intros"])
    assert labels[True] >= 5
    assert labels[False] >= 5
    difficulties = {item["difficulty"] for item in dataset["intros"] if item["expect"]}
    assert {"spelled-out", "address", "obfuscated"} <= difficulties


def test_summarize_counts_a_crisis_parse_escalation_as_a_failed_call() -> None:
    """A repeated parse failure escalates to a crisis match; it must still show as failed."""
    escalated = Outcome(
        item_id="x",
        check="crisis",
        difficulty="plain",
        language="en",
        expected=True,
        predicted=True,
        failure="parse",
        latency_s=0.0,
    )

    summary = summarize([escalated])["crisis"]

    assert summary.failed == 1
    assert summary.tp == 1
