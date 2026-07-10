"""Evaluate answer quality using Ragas answer-centric metrics.

Measures:
  - Faithfulness: whether the answer is grounded in the retrieved context
  - AnswerRelevancy: how relevant the answer is to the question
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
    faithfulness,
)

logger = logging.getLogger(__name__)


@pytest.mark.ragas
def test_faithfulness(evaluation_dataset, ragas_llm, ragas_embeddings, ragas_run_config):
    """Faithfulness: whether the answer is grounded in retrieved context."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[faithfulness],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        run_config=ragas_run_config,
    )
    score = result["faithfulness"]
    score_val = score[0] if isinstance(score, list) else score
    logger.info("Faithfulness: %.4f (threshold=0.70)", score_val)
    assert score_val >= 0.7, f"Faithfulness {score_val:.4f} < 0.70"


@pytest.mark.ragas
def test_answer_relevancy(evaluation_dataset, ragas_llm, ragas_embeddings, ragas_run_config):
    """AnswerRelevancy: how relevant the answer is to the question."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[answer_relevancy],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        run_config=ragas_run_config,
    )
    score = result["answer_relevancy"]
    score_val = score[0] if isinstance(score, list) else score
    logger.info("AnswerRelevancy: %.4f (threshold=0.70)", score_val)
    assert score_val >= 0.7, f"AnswerRelevancy {score_val:.4f} < 0.70"


@pytest.mark.ragas
def test_answer_correctness(evaluation_dataset, ragas_llm, ragas_embeddings, ragas_run_config):
    """AnswerCorrectness: alignment between answer and ground truth."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[answer_correctness],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        run_config=ragas_run_config,
    )
    score = result["answer_correctness"]
    score_val = score[0] if isinstance(score, list) else score
    logger.info("AnswerCorrectness: %.4f (threshold=0.50)", score_val)
    assert score_val >= 0.5, f"AnswerCorrectness {score_val:.4f} < 0.50"


@pytest.mark.ragas
def test_answer_similarity(evaluation_dataset, ragas_llm, ragas_embeddings, ragas_run_config):
    """AnswerSimilarity: semantic similarity between answer and ground truth."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[answer_similarity],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        run_config=ragas_run_config,
    )
    score = result["answer_similarity"]
    score_val = score[0] if isinstance(score, list) else score
    logger.info("AnswerSimilarity: %.4f (threshold=0.70)", score_val)
    assert score_val >= 0.7, f"AnswerSimilarity {score_val:.4f} < 0.70"
