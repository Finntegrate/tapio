"""Guardrails for sensitive and off-topic queries (#29): classify before routing."""

from app.guardrails.classifier import GuardrailCategory, GuardrailClassifierProtocol, GuardrailMatch
from app.guardrails.llm_classifier import LLMGuardrailClassifier
from app.guardrails.resources import CrisisResource, CrisisResourceList, load_crisis_resources
from app.guardrails.responses import build_guardrail_response

__all__ = [
    "CrisisResource",
    "CrisisResourceList",
    "GuardrailCategory",
    "GuardrailClassifierProtocol",
    "GuardrailMatch",
    "LLMGuardrailClassifier",
    "build_guardrail_response",
    "load_crisis_resources",
]
