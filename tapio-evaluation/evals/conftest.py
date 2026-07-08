"""Shared fixtures for DeepEval evaluation tests.

Provides:
- Parametrized test cases spanning all evaluation datasets
- Session-scoped fixtures for the Ollama judge, RAG orchestrator, and rubrics
"""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = EVAL_DIR / "datasets"
RUBRICS_DIR = EVAL_DIR / "rubrics"

DATASET_NAMES = [
    "citizenship",
    "dvv",
    "edge_cases",
    "healthcare",
    "housing",
    "kela",
    "residence_permits",
    "taxes",
    "work_rights",
]


def load_dataset(name: str) -> list[dict[str, Any]]:
    path = DATASETS_DIR / f"{name}.jsonl"
    cases: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                cases.append(json.loads(stripped))
    return cases


def load_rubric(name: str) -> str:
    return (RUBRICS_DIR / f"{name}.md").read_text()


# Collect every test case across all datasets into one parametrized fixture.
# Each item is a (dataset_name, case_dict) tuple.
_ALL_CASES: list[tuple[str, dict[str, Any]]] = []
_ALL_IDS: list[str] = []
for _name in DATASET_NAMES:
    for _case in load_dataset(_name):
        _ALL_CASES.append((_name, _case))
        _ALL_IDS.append(f"{_name}:{_case['test_case_id']}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=_ALL_CASES,
    ids=_ALL_IDS,
)
def case(request) -> tuple[str, dict[str, Any]]:
    """Parametrized fixture yielding every evaluation test case.

    Each invocation yields a (dataset_name, case_dict) tuple.
    """
    return request.param


@pytest.fixture(scope="session")
def rubrics() -> dict[str, str]:
    return {
        "correctness": load_rubric("correctness"),
        "safety": load_rubric("safety"),
        "retrieval": load_rubric("retrieval"),
    }


@pytest.fixture(scope="session")
def ollama_judge():
    """Configure DeepEval to use a local Ollama model as the evaluation judge."""
    import ollama
    from deepeval.models import OllamaModel

    try:
        ollama.list()
    except Exception as e:
        pytest.skip(f"Ollama is not available: {e}")

    return OllamaModel(
        model="llama3.2",
        base_url="http://localhost:11434",
        temperature=0,
    )


@pytest.fixture(scope="session")
def rag_orchestrator():
    """Create a real RAG orchestrator wired to the persisted ChromaDB store."""
    from tapio.config.config_models import RAGConfig
    from tapio.factories import RAGOrchestratorFactory

    config = RAGConfig()
    factory = RAGOrchestratorFactory(config)
    orchestrator = factory.create_orchestrator()

    if not orchestrator.check_model_availability():
        pytest.skip("LLM model is not available in Ollama")

    return orchestrator
