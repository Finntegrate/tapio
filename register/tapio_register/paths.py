"""Filesystem locations of the register's source, generated, and released files."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SERVICE_DIR = PACKAGE_DIR.parent

#: The LinkML schema every other artifact is derived from.
SCHEMA_PATH = PACKAGE_DIR / "schema" / "term_register.yaml"

#: Hand-curated register source, reviewed by a person before it lands.
SOURCE_PATH = PACKAGE_DIR / "data" / "register.yaml"

#: Artifacts LinkML generates from ``SCHEMA_PATH``. Checked in, never hand-edited.
GENERATED_DIR = PACKAGE_DIR / "generated"
PYDANTIC_PATH = GENERATED_DIR / "term_register_model.py"
JSON_SCHEMA_PATH = GENERATED_DIR / "term_register.schema.json"
SHACL_PATH = GENERATED_DIR / "term_register.shapes.ttl"

#: One immutable directory per dated edition.
RELEASES_DIR = SERVICE_DIR / "releases"

#: Where ``tapio-register seed`` leaves candidates for human review.
CANDIDATES_DIR = SERVICE_DIR / "candidates"


def release_dir(version: str) -> Path:
    """Return the directory holding the edition released on ``version``."""
    return RELEASES_DIR / version
