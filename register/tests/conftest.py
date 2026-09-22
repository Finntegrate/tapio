"""Fixtures shared by the register tests."""

import copy
from typing import Any

import pytest

from tapio_register.generated.term_register_model import TermRegister

MIGRI_URL = "https://migri.fi/en/residence-permit"


def observation(**overrides: Any) -> dict[str, Any]:
    """A minimal, valid observation."""
    return {"source": "migri", "url": MIGRI_URL, "observed_on": "2026-09-19"} | overrides


def concept(concept_id: str, **overrides: Any) -> dict[str, Any]:
    """A minimal, valid concept, with overrides applied on top."""
    base: dict[str, Any] = {
        "id": concept_id,
        "kind": "permit",
        "pref_label": {"en": concept_id, "fi": f"{concept_id} fi", "sv": f"{concept_id} sv"},
        "valid_from": "2004-05-01",
        "in_scope_of": ["ilmarinen"],
        "observations": [observation()],
    }
    return base | overrides


@pytest.fixture
def register_dict() -> dict[str, Any]:
    """A small but complete register, used as the base for the rule tests."""
    return {
        "register_version": "2026-09-19",
        "title": "Test register",
        "description": "A register used by the tests.",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "coverage_caveat": "Records what its sources said, not ground truth.",
        "concepts": [
            concept(
                "permit:first-residence-permit",
                broader=["permit:residence-permit"],
                handled_by=["org:migri"],
            ),
            concept("permit:residence-permit"),
            concept("org:migri", kind="organization"),
        ],
    }


@pytest.fixture
def register(register_dict: dict[str, Any]) -> TermRegister:
    """The fixture register, parsed."""
    return TermRegister.model_validate(copy.deepcopy(register_dict))
