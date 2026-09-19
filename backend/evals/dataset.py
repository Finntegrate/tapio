"""Golden question set shared by the retrieval and generation evaluations."""

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GOLDEN_SET = Path(__file__).parent / "golden_set.jsonl"


@dataclass(frozen=True)
class GoldenCase:
    """One evaluation question with the sources and facts a good result contains.

    Attributes:
        id: Stable identifier used in reports.
        question: The user question, in Finnish or English.
        language: Language code of the question (``fi`` or ``en``).
        expected_source_urls: Pages that should be retrieved. Any one counts as a hit.
        key_facts: Statements a correct answer must convey. Empty means the
            answer is not scored for correctness.
    """

    id: str
    question: str
    language: str
    expected_source_urls: tuple[str, ...]
    key_facts: tuple[str, ...] = ()


def load_golden_set(path: Path = DEFAULT_GOLDEN_SET) -> list[GoldenCase]:
    """Load golden cases from a JSON Lines file.

    Args:
        path: File with one JSON object per line. Blank lines are ignored.

    Returns:
        The parsed cases in file order.

    Raises:
        ValueError: If a line is missing a required field or ids repeat.
    """
    cases: list[GoldenCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        missing = {"id", "question", "language", "expected_source_urls"} - raw.keys()
        if missing:
            msg = f"{path.name}:{line_number} is missing fields: {sorted(missing)}"
            raise ValueError(msg)
        if raw["id"] in seen_ids:
            msg = f"{path.name}:{line_number} repeats id '{raw['id']}'"
            raise ValueError(msg)
        seen_ids.add(raw["id"])
        cases.append(
            GoldenCase(
                id=raw["id"],
                question=raw["question"],
                language=raw["language"],
                expected_source_urls=tuple(raw["expected_source_urls"]),
                key_facts=tuple(raw.get("key_facts", [])),
            )
        )
    return cases
