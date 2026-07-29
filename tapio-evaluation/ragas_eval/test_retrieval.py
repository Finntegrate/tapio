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
def test_context_precision(evaluation_dataset, ragas_llm, ragas_embeddings, ragas_run_config):
    """ContextPrecision: signal-to-noise ratio in retrieved contexts."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[context_precision],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        run_config=ragas_run_config,
    )
    score = result["context_precision"]
    score_val = score[0] if isinstance(score, list) else score
    logger.info("ContextPrecision: %.4f (threshold=0.50)", score_val)
    assert score_val >= 0.5, f"ContextPrecision {score_val:.4f} < 0.50"


@pytest.mark.ragas
def test_context_recall(evaluation_dataset, ragas_llm, ragas_embeddings, ragas_run_config):
    """ContextRecall: whether ground truth is covered by retrieved contexts."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[context_recall],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        run_config=ragas_run_config,
    )
    score = result["context_recall"]
    score_val = score[0] if isinstance(score, list) else score
    logger.info("ContextRecall: %.4f (threshold=0.50)", score_val)
    assert score_val >= 0.5, f"ContextRecall {score_val:.4f} < 0.50"
