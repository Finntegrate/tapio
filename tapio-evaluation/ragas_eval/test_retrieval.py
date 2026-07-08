"""Evaluate retrieval quality using Ragas context metrics.

Measures:
  - ContextPrecision: whether retrieved documents contain relevant information
  - ContextRecall: whether retrieved documents cover the ground truth
"""

import logging

import pytest
from ragas import evaluate
from ragas.metrics import context_precision, context_recall

logger = logging.getLogger(__name__)


@pytest.mark.ragas
def test_context_precision(evaluation_dataset, ragas_llm, ragas_embeddings):
    """ContextPrecision: signal-to-noise ratio in retrieved contexts."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[context_precision],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
    score = result["context_precision"]
    logger.info("ContextPrecision: %.4f (threshold=0.50)", score)
    assert score >= 0.5, f"ContextPrecision {score:.4f} < 0.50"


@pytest.mark.ragas
def test_context_recall(evaluation_dataset, ragas_llm, ragas_embeddings):
    """ContextRecall: whether ground truth is covered by retrieved contexts."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[context_recall],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
    score = result["context_recall"]
    logger.info("ContextRecall: %.4f (threshold=0.50)", score)
    assert score >= 0.5, f"ContextRecall {score:.4f} < 0.50"
