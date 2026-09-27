"""Tests for the FastAPI app's startup wiring in app.main.lifespan."""

from unittest.mock import Mock, patch

from fastapi import FastAPI
from langchain_core.language_models import BaseChatModel

from app.guardrails import LLMGuardrailClassifier
from app.guardrails.llm_classifier import GuardrailCheckResult
from app.main import lifespan


async def test_lifespan_wires_the_same_llm_into_orchestrator_and_guardrail_classifier() -> None:
    """The guardrail classifier must run its safety checks on the exact chat model the
    orchestrator generates answers with (#9), not a separately constructed one — otherwise
    a non-Ollama provider's safety checks silently point at the wrong backend.

    ``LLMGuardrailClassifier`` doesn't store the model it's given; it stores the result of
    ``model.with_structured_output(...)``, a wrapped object with no reliable way back to the
    original instance. So instead of asserting identity on that wrapper, this asserts that
    ``with_structured_output`` was called on the exact mock the orchestrator was given —
    which only happens if the classifier was built from that same instance.
    """
    fake_llm = Mock(spec=BaseChatModel)
    fake_orchestrator = Mock()
    fake_orchestrator.llm_service = fake_llm
    fake_orchestrator.graph = Mock()

    fake_factory = Mock()
    fake_factory.create_orchestrator.return_value = fake_orchestrator

    app = FastAPI()

    with patch("app.main.RAGOrchestratorFactory", return_value=fake_factory):
        async with lifespan(app):
            assert app.state.orchestrator is fake_orchestrator
            assert app.state.orchestrator_graph is fake_orchestrator.graph
            assert isinstance(app.state.guardrail_classifier, LLMGuardrailClassifier)
            fake_llm.with_structured_output.assert_called_once_with(GuardrailCheckResult)
