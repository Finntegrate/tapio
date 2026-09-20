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


class StrictLoader(yaml.SafeLoader):
    """A safe loader that refuses a duplicate mapping key instead of taking the last.

    The register is hand-curated YAML, so a key written twice is a real
    possibility — two ``pref_label`` blocks after a careless paste, two
    ``valid_until`` lines after an edit. PyYAML's default is last-write-wins and
    silent, which would let one of them disappear before any validation rule
    could look at it. Here that is an error at the point of reading.
    """

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:  # noqa: FBT001, FBT002
        """Construct a mapping, rejecting any key that appears more than once."""
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                mark = key_node.start_mark
                message = f"{mark.name}, line {mark.line + 1}: duplicate key {key!r}"
                raise ValueError(message)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(path: Path) -> Any:
    """Read one YAML file the way correctness-critical data has to be read."""
    with path.open(encoding="utf-8") as handle:
        return yaml.load(handle, Loader=StrictLoader)  # noqa: S506 - StrictLoader derives from SafeLoader


def read_source(source_path: Path | None = None) -> dict[str, Any]:
    """Return the raw register source as a dict, without validating it.

    Accepts either the data directory, where edition metadata and one file per
    kind are assembled into a single register, or a single file holding a whole
    register. The second form is what a released edition's snapshot is, and what
    tests build.
    """
    path = source_path or paths.SOURCE_PATH
    loaded = _read_directory(path) if path.is_dir() else load_yaml(path)
    if not isinstance(loaded, dict):
        message = f"{path} does not contain a register mapping"
        raise TypeError(message)
    return loaded


def _read_directory(path: Path) -> dict[str, Any]:
    """Assemble the edition metadata and every kind's concepts into one register.

    A concept in the wrong file is an error rather than a warning: the file a
    concept lives in is derivable from its kind, so a mismatch means one of the
    two is wrong and neither can be assumed.
    """
    register: dict[str, Any] = load_yaml(path / paths.EDITION_NAME)
    concepts: list[dict[str, Any]] = []
    for kind, filename in paths.KIND_FILES.items():
        part = path / filename
        if not part.exists():
            # A kind file that is absent would otherwise read as a kind with no
            # concepts, and a partial register is worse than no register: the
            # projections would simply stop offering everything in it.
            message = f"{part} is missing, so the register would load without its {kind} concepts"
            raise FileNotFoundError(message)
        for concept in (load_yaml(part) or {}).get("concepts") or []:
            if concept.get("kind") != kind:
                message = f"{filename} holds '{concept.get('id')}', which is a {concept.get('kind')}"
                raise ValueError(message)
            concepts.append(concept)
    register["concepts"] = concepts
    return register


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
