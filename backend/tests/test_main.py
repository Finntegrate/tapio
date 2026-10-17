"""Tests for the FastAPI app's startup wiring in app.main.lifespan."""

from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from langchain_core.language_models import BaseChatModel

from app.config.llm_settings import GUARDRAIL_ROLE
from app.guardrails import LLMGuardrailClassifier
from app.guardrails.llm_classifier import GuardrailCheckResult
from app.main import lifespan


@pytest.mark.parametrize("shares_generation_model", [True, False])
async def test_lifespan_shares_one_role_aware_guardrail_model_with_the_classifier_and_health(
    *,
    shares_generation_model: bool,
) -> None:
    """The guardrail's model is built once via ``factory.create_chat_model(role=GUARDRAIL_ROLE)``.

    That one instance goes both to the classifier and to the orchestrator (which ``/health``
    checks), so a broken guardrail model can't hide behind a second, separately built instance.
    A distinct mock stands in for the orchestrator's own model so this would fail if the
    wiring reused ``orchestrator.llm_service`` instead (#139).

    ``LLMGuardrailClassifier`` doesn't store the model it's given; it stores the result of
    ``model.with_structured_output(...)``, so this asserts that call landed on the right mock.
    """
    fake_orchestrator_llm = Mock(spec=BaseChatModel)
    fake_guardrail_llm = Mock(spec=BaseChatModel)
    fake_orchestrator = Mock()
    fake_orchestrator.llm_service = fake_orchestrator_llm
    fake_orchestrator.graph = Mock()

    fake_factory = Mock()
    fake_factory.create_orchestrator.return_value = fake_orchestrator
    fake_factory.create_chat_model.return_value = fake_guardrail_llm
    fake_factory.guardrail_shares_default_model.return_value = shares_generation_model

    app = FastAPI()

    with (
        patch("app.main.RAGOrchestratorFactory", return_value=fake_factory),
        patch("app.main.LLMGuardrailClassifier", wraps=LLMGuardrailClassifier) as classifier_cls,
    ):
        async with lifespan(app):
            assert app.state.orchestrator is fake_orchestrator
            assert app.state.orchestrator_graph is fake_orchestrator.graph
            assert isinstance(app.state.guardrail_classifier, LLMGuardrailClassifier)
            fake_factory.create_chat_model.assert_called_once_with(role=GUARDRAIL_ROLE)
            fake_factory.create_orchestrator.assert_called_once_with(guardrail_model=fake_guardrail_llm)
            classifier_cls.assert_called_once_with(fake_guardrail_llm, shares_generation_model=shares_generation_model)
            fake_guardrail_llm.with_structured_output.assert_called_once_with(GuardrailCheckResult)
            fake_orchestrator_llm.with_structured_output.assert_not_called()
