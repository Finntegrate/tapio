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
def test_faithfulness(evaluation_dataset, ragas_llm, ragas_embeddings):
    """Faithfulness: whether the answer is grounded in retrieved context."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[faithfulness],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
    score = result["faithfulness"]
    logger.info("Faithfulness: %.4f (threshold=0.70)", score)
    assert score >= 0.7, f"Faithfulness {score:.4f} < 0.70"


@pytest.mark.ragas
def test_answer_relevancy(evaluation_dataset, ragas_llm, ragas_embeddings):
    """AnswerRelevancy: how relevant the answer is to the question."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[answer_relevancy],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
    score = result["answer_relevancy"]
    logger.info("AnswerRelevancy: %.4f (threshold=0.70)", score)
    assert score >= 0.7, f"AnswerRelevancy {score:.4f} < 0.70"


@pytest.mark.ragas
def test_answer_correctness(evaluation_dataset, ragas_llm, ragas_embeddings):
    """AnswerCorrectness: alignment between answer and ground truth."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[answer_correctness],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
    score = result["answer_correctness"]
    logger.info("AnswerCorrectness: %.4f (threshold=0.50)", score)
    assert score >= 0.5, f"AnswerCorrectness {score:.4f} < 0.50"


@pytest.mark.ragas
def test_answer_similarity(evaluation_dataset, ragas_llm, ragas_embeddings):
    """AnswerSimilarity: semantic similarity between answer and ground truth."""
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=[answer_similarity],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
    score = result["answer_similarity"]
    logger.info("AnswerSimilarity: %.4f (threshold=0.70)", score)
    assert score >= 0.7, f"AnswerSimilarity {score:.4f} < 0.70"
