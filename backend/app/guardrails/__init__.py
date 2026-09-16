"""Guardrails for sensitive and off-topic queries (#29): classify before routing."""

from app.guardrails.classifier import GuardrailCategory, GuardrailClassifier, GuardrailMatch
from app.guardrails.resources import CrisisResource, CrisisResourceList, load_crisis_resources
from app.guardrails.responses import build_guardrail_response

__all__ = [
    "CrisisResource",
    "CrisisResourceList",
    "GuardrailCategory",
    "GuardrailClassifier",
    "GuardrailMatch",
    "build_guardrail_response",
    "load_crisis_resources",
]
