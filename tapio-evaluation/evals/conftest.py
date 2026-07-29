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

MULTI_TURN_DATASETS = [
    "multi_turn_conversations",
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
        model="qwen2.5:7b",
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


# ---------------------------------------------------------------------------
# Multi-turn conversation fixtures
# ---------------------------------------------------------------------------


def _load_multi_turn_cases(name: str) -> list[dict[str, Any]]:
    """Load multi-turn test cases and parse turns into dicts."""
    return load_dataset(name)


# Collect all multi-turn test cases
_MT_CASES: list[tuple[str, dict[str, Any]]] = []
_MT_IDS: list[str] = []
for _name in MULTI_TURN_DATASETS:
    for _case in _load_multi_turn_cases(_name):
        _MT_CASES.append((_name, _case))
        _MT_IDS.append(f"{_name}:{_case['test_case_id']}")


@pytest.fixture(params=_MT_CASES, ids=_MT_IDS)
def multi_turn_case(request) -> tuple[str, dict[str, Any]]:
    """Parametrized fixture yielding every multi-turn conversation test case."""
    return request.param


@pytest.fixture(scope="session")
def conversation_runner(rag_orchestrator):
    """Create a ConversationRunner wired to the session-scoped orchestrator."""
    from tapio.evaluation import ConversationRunner

    return ConversationRunner(rag_orchestrator)
