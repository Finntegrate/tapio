"""Read the curated register source into the generated Pydantic classes."""

from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from tapio_register import paths
from tapio_register.generated.term_register_model import Concept, TermRegister

#: The IRI prefix each ``kind`` must use, so that an IRI alone says what it denotes.
KIND_PREFIXES: dict[str, str] = {
    "organization": "org",
    "permit": "permit",
    "step": "step",
    "document": "doc",
    "status": "status",
    "service": "svc",
    "legal_act": "law",
    "term": "term",
}

#: What each CURIE prefix expands to when the register is published as RDF.
PREFIX_NAMESPACES: dict[str, str] = {
    "org": "https://tapio.finntegrate.org/register/organization/",
    "permit": "https://tapio.finntegrate.org/register/permit/",
    "step": "https://tapio.finntegrate.org/register/step/",
    "doc": "https://tapio.finntegrate.org/register/document/",
    "status": "https://tapio.finntegrate.org/register/status/",
    "svc": "https://tapio.finntegrate.org/register/service/",
    "law": "https://tapio.finntegrate.org/register/legal-act/",
    "term": "https://tapio.finntegrate.org/register/term/",
}

#: The scheme every concept in the register belongs to.
SCHEME_IRI = "https://tapio.finntegrate.org/register/scheme"

#: Namespace the per-guide scope collections are minted under.
GUIDE_COLLECTION_BASE = "https://tapio.finntegrate.org/register/guide/"

#: Namespace for register-local RDF predicates and classes.
TAPIO_NAMESPACE = "https://tapio.finntegrate.org/schema/"


def read_source(source_path: Path | None = None) -> dict[str, Any]:
    """Return the raw register source as a dict, without validating it."""
    path = source_path or paths.SOURCE_PATH
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        message = f"{path} does not contain a register mapping"
        raise TypeError(message)
    return loaded


def load_register(source_path: Path | None = None) -> TermRegister:
    """Load and structurally validate the register source.

    Raises ``pydantic.ValidationError`` when the source does not satisfy the
    schema. Cross-concept rules live in :mod:`tapio_register.validation`.
    """
    return TermRegister.model_validate(read_source(source_path))


def concepts_by_id(register: TermRegister) -> dict[str, Concept]:
    """Index a register's concepts by IRI."""
    return {concept.id: concept for concept in register.concepts}


def enum_value(value: object) -> str:
    """Return a LinkML enum slot's value as a string.

    The generated model is configured with ``use_enum_values``, so these slots
    hold plain strings at runtime while the class annotations name the enum.
    """
    return value.value if isinstance(value, Enum) else str(value)


def expand(curie: str) -> str:
    """Expand a register CURIE to a full IRI, leaving full IRIs untouched."""
    prefix, separator, local = curie.partition(":")
    if separator and prefix in PREFIX_NAMESPACES:
        return PREFIX_NAMESPACES[prefix] + local
    return curie
