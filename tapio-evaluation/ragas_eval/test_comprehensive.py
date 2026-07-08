"""Full RAG pipeline evaluation using Ragas metrics.

Runs all available metrics on the complete evaluation dataset to provide a
holistic view of pipeline performance. Individual test files cover specific
metric groups for faster iteration.

Metrics:
  - Faithfulness: whether the answer is grounded in retrieved context
  - AnswerRelevancy: how relevant the answer is to the question
  - ContextPrecision: signal-to-noise ratio in retrieved contexts
  - ContextRecall: whether ground truth is covered by retrieved contexts
  - AnswerCorrectness: alignment between answer and ground truth
  - AnswerSimilarity: semantic similarity between answer and ground truth
"""

import logging

import pytest
from ragas import evaluate
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    answer_similarity,
    context_precision,
    context_recall,
    faithfulness,
)

logger = logging.getLogger(__name__)

# Score thresholds — answers below these are considered failures
_THRESHOLDS: dict[str, float] = {
    "faithfulness": 0.7,
    "answer_relevancy": 0.7,
    "context_precision": 0.5,
    "context_recall": 0.5,
    "answer_correctness": 0.5,
    "answer_similarity": 0.7,
}

_ALL_METRICS = [
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
    answer_similarity,
]


@pytest.mark.ragas
def test_comprehensive_evaluation(evaluation_dataset, ragas_llm, ragas_embeddings):
    """Run all Ragas metrics on the full evaluation dataset."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=_ALL_METRICS,
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )

    logger.info("Ragas comprehensive evaluation results:")
    for metric_name, score in result.items():
        threshold = _THRESHOLDS.get(metric_name, 0.0)
        status = "PASS" if score >= threshold else "FAIL"
        logger.info("  %s: %.4f (threshold=%.2f) [%s]", metric_name, score, threshold, status)

    for metric_name, score in result.items():
        threshold = _THRESHOLDS.get(metric_name, 0.0)
        assert score >= threshold, f"{metric_name} score {score:.4f} is below threshold {threshold:.2f}"
