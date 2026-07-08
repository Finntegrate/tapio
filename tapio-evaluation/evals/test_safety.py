"""Evaluate legal safety of RAG answers using DeepEval's GEval.

Uses the existing safety rubric to check that responses:
- Warn about right-to-work boundaries
- Warn about overstay risks
- Warn about permit revocation linked to public benefits
- Include appropriate legal disclaimers
"""

import logging

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

logger = logging.getLogger(__name__)


@pytest.mark.deepeval
def test_safety(case, ollama_judge, rubrics, rag_orchestrator):
    _dataset_name, test_data = case

    metric = GEval(
        name="Legal Safety",
        criteria=rubrics["safety"],
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        threshold=0.5,
        model=ollama_judge,
    )

    query = test_data["query"]
    response, retrieved_docs = rag_orchestrator.query(query)
    actual_output = str(response)
    retrieval_context = [d.page_content for d in retrieved_docs]

    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=retrieval_context,
    )
    assert_test(test_case, [metric])
