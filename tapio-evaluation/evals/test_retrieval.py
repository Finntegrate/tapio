"""Evaluate retrieval and grounding quality using DeepEval's RAG metrics.

Measures:
- Faithfulness: whether the answer is grounded in the retrieved context
- Answer Relevancy: whether the answer is relevant to the query
"""

import logging

import pytest
from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase

logger = logging.getLogger(__name__)


@pytest.mark.deepeval
def test_retrieval(case, ollama_judge, rag_orchestrator):
    _dataset_name, test_data = case

    faithfulness = FaithfulnessMetric(
        threshold=0.7,
        model=ollama_judge,
        include_reason=True,
    )
    relevance = AnswerRelevancyMetric(
        threshold=0.7,
        model=ollama_judge,
        include_reason=True,
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
    assert_test(test_case, [faithfulness, relevance])
