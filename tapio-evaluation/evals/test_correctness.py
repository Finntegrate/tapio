"""Evaluate factual correctness of RAG answers against expected answers.

Uses DeepEval's GEval with the existing correctness rubric to score how
well the generated answer aligns with the ground-truth reference answer.
"""

import logging

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

logger = logging.getLogger(__name__)


@pytest.mark.deepeval
def test_correctness(case, ollama_judge, rubrics, rag_orchestrator):
    _dataset_name, test_data = case

    metric = GEval(
        name="Factual Correctness",
        criteria=rubrics["correctness"],
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        threshold=0.5,
        model=ollama_judge,
    )

    query = test_data["query"]
    expected = test_data["expected_answer"]
    response, retrieved_docs = rag_orchestrator.query(query)
    actual_output = str(response)
    retrieval_context = [d.page_content for d in retrieved_docs]

    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        expected_output=expected,
        retrieval_context=retrieval_context,
    )
    assert_test(test_case, [metric])
