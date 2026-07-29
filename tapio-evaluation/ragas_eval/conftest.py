"""Shared fixtures for Ragas evaluation tests.

Provides:
- A compatibility patch for langchain-community / ragas import issue
- Session-scoped Ragas LLM and embeddings wrappers
- A parametrised fixture that builds a HuggingFace Dataset from all test cases
"""

import json
import logging
import os
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = EVAL_DIR / "datasets"

_ALL_DATASET_NAMES = [
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

RAGAS_DATASETS = os.environ.get("RAGAS_DATASETS")
DATASET_NAMES: list[str] = [d.strip() for d in RAGAS_DATASETS.split(",")] if RAGAS_DATASETS else _ALL_DATASET_NAMES

RAGAS_CASES = os.environ.get("RAGAS_CASES")
_CASE_FILTER: set[str] | None = {c.strip() for c in RAGAS_CASES.split(",")} if RAGAS_CASES else None

# ---------------------------------------------------------------------------
# Ragas compatibility patch
# ---------------------------------------------------------------------------
# Ragas 0.3.x eagerly imports langchain_community.chat_models.vertexai and
# langchain_community.llms.vertexai, which were removed from later releases
# of langchain-community. We inject minimal stubs before ragas is loaded.


def _apply_ragas_patch() -> None:
    import sys

    if "ragas" in sys.modules:
        return  # already imported, patch must already be in place

    class _StubChatVertexAI:
        pass

    class _StubVertexAI:
        pass

    chat_mod = ModuleType("langchain_community.chat_models.vertexai")
    chat_mod.ChatVertexAI = _StubChatVertexAI
    chat_mod.__package__ = "langchain_community.chat_models.vertexai"

    llm_mod = ModuleType("langchain_community.llms.vertexai")
    llm_mod.VertexAI = _StubVertexAI
    llm_mod.__package__ = "langchain_community.llms.vertexai"

    sys.modules["langchain_community.chat_models.vertexai"] = chat_mod
    sys.modules["langchain_community.llms.vertexai"] = llm_mod

    for parent_name, child_mod in [
        ("langchain_community.chat_models", chat_mod),
        ("langchain_community.llms", llm_mod),
    ]:
        parent = sys.modules.get(parent_name)
        if parent is not None:
            parent.vertexai = child_mod

    logger.info("Ragas compatibility patch applied")


_apply_ragas_patch()

# Now safe to import ragas
from datasets import Dataset  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402


def load_dataset(name: str) -> list[dict[str, Any]]:
    path = DATASETS_DIR / f"{name}.jsonl"
    cases: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                cases.append(json.loads(stripped))
    return cases


# Collect every test case across all datasets
_ALL_CASES: list[tuple[str, dict[str, Any]]] = []
_ALL_IDS: list[str] = []
for _name in DATASET_NAMES:
    for _case in load_dataset(_name):
        _cid = _case["test_case_id"]
        if _CASE_FILTER is not None and _cid not in _CASE_FILTER:
            continue
        _ALL_CASES.append((_name, _case))
        _ALL_IDS.append(f"{_name}:{_cid}")

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
def ragas_llm():
    """Session-scoped Ragas LangchainLLMWrapper backed by local Ollama."""
    from langchain_ollama import ChatOllama

    try:
        import ollama

        ollama.list()
    except Exception as e:
        pytest.skip(f"Ollama is not available: {e}")

    model = os.environ.get("RAGAS_LLM_MODEL", "qwen2.5:7b")
    chat = ChatOllama(
        model=model,
        base_url="http://localhost:11434",
        temperature=0,
    )
    return LangchainLLMWrapper(chat)


@pytest.fixture(scope="session")
def ragas_run_config():
    """Session-scoped RunConfig with relaxed timeout for local Ollama."""
    from ragas.run_config import RunConfig

    timeout = int(os.environ.get("RAGAS_TIMEOUT", "600"))
    return RunConfig(timeout=timeout)


@pytest.fixture(scope="session")
def ragas_embeddings():
    """Session-scoped Ragas embeddings wrapper using the project's embedding model."""
    from langchain_huggingface import HuggingFaceEmbeddings

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return LangchainEmbeddingsWrapper(embeddings)


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


@pytest.fixture(scope="session")
def evaluation_dataset(rag_orchestrator) -> Dataset:
    """Build a HuggingFace Dataset from all test cases by running the RAG pipeline.

    Each row contains:
      - user_input: the original query
      - response: the generated answer
      - retrieved_contexts: list of retrieved document chunks
      - reference: the ground-truth expected answer
    """
    rows: list[dict[str, Any]] = []
    for name in DATASET_NAMES:
        for test_data in load_dataset(name):
            if _CASE_FILTER is not None and test_data["test_case_id"] not in _CASE_FILTER:
                continue
            query = test_data["query"]
            try:
                response, retrieved_docs = rag_orchestrator.query(query)
                actual_output = str(response)
                contexts = [d.page_content for d in retrieved_docs]
            except Exception:
                logger.exception("Failed to process query: %s", query)
                actual_output = ""
                contexts = []

            rows.append(
                {
                    "user_input": query,
                    "response": actual_output,
                    "retrieved_contexts": contexts,
                    "reference": test_data["expected_answer"],
                },
            )

    return Dataset.from_list(rows)
