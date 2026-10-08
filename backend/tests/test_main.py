"""Tests for the FastAPI app's startup wiring in app.main.lifespan."""

from unittest.mock import Mock, patch

from fastapi import FastAPI
from langchain_core.language_models import BaseChatModel

from app.config.llm_settings import GUARDRAIL_ROLE
from app.guardrails import LLMGuardrailClassifier
from app.guardrails.llm_classifier import GuardrailCheckResult
from app.main import lifespan


async def test_lifespan_builds_the_guardrail_classifier_through_the_role_aware_factory_path() -> None:
    """The guardrail classifier must be built via ``factory.create_chat_model(role=GUARDRAIL_ROLE)``
    — the same configured-provider path (#9) the orchestrator's own model goes through, with
    its own ``TAPIO_LLM_MODEL_OVERRIDES`` slot (#139) — not a separately, differently
    constructed model that bypasses that configuration.

    As of #204, the guardrail's model is no longer necessarily the exact same object as
    ``orchestrator.llm_service`` (per-stage overrides mean they can legitimately differ); what
    must hold is that it still comes from the factory's configured, role-aware path. A
    distinct mock stands in for the orchestrator's own model so this test would fail if the
    wiring were changed to (incorrectly) reuse ``orchestrator.llm_service`` instead of calling
    ``create_chat_model(role=GUARDRAIL_ROLE)``.

    ``LLMGuardrailClassifier`` doesn't store the model it's given; it stores the result of
    ``model.with_structured_output(...)``, a wrapped object with no reliable way back to the
    original instance. So instead of asserting identity on that wrapper, this asserts that
    ``with_structured_output`` was called on the exact mock ``create_chat_model`` returned.
    """
    fake_orchestrator_llm = Mock(spec=BaseChatModel)
    fake_guardrail_llm = Mock(spec=BaseChatModel)
    fake_orchestrator = Mock()
    fake_orchestrator.llm_service = fake_orchestrator_llm
    fake_orchestrator.graph = Mock()

    fake_factory = Mock()
    fake_factory.create_orchestrator.return_value = fake_orchestrator
    fake_factory.create_chat_model.return_value = fake_guardrail_llm

    app = FastAPI()

    with patch("app.main.RAGOrchestratorFactory", return_value=fake_factory):
        async with lifespan(app):
            assert app.state.orchestrator is fake_orchestrator
            assert app.state.orchestrator_graph is fake_orchestrator.graph
            assert isinstance(app.state.guardrail_classifier, LLMGuardrailClassifier)
            fake_factory.create_chat_model.assert_called_once_with(role=GUARDRAIL_ROLE)
            fake_guardrail_llm.with_structured_output.assert_called_once_with(GuardrailCheckResult)
            fake_orchestrator_llm.with_structured_output.assert_not_called()
