"""Evaluate retrieval quality and context relevance using DeepEval's GEval.

Uses the retrieval rubric to score how well the retrieved context chunks
match the query in topic, agency precision, and noise level.
"""

import logging

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

logger = logging.getLogger(__name__)


@pytest.mark.deepeval
def test_retrieval(case, ollama_judge, rubrics, rag_orchestrator):
    _dataset_name, test_data = case

    metric = GEval(
        name="Retrieval Quality",
        criteria=rubrics["retrieval"],
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT,
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
