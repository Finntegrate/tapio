"""Guide scope is written down in several places, and they have to agree.

The roster at finntegrate.org is canonical, PRD §6 mirrors it, CLAUDE.md copies
it for agent context, and the register marks each concept with the guides whose
remit it falls within. Four representations of one fact, three of which can
drift silently - and one already did: CLAUDE.md had Sampo on financial
requirements and Rauni on work permits long after the roster moved Sampo to
employment and Rauni to benefits, which is the table the register was first
seeded against.

Deriving the documentation and the backend's guide definitions from the
register is the real fix, and it is what the milestone's scope-as-concept-sets
work is for. Until then, this makes the drift loud.
"""

import re
from pathlib import Path

import pytest

from tapio_register import loading, paths
from tapio_register.generated.term_register_model import GuideId

REPO_ROOT = paths.SERVICE_DIR.parent
PRD = REPO_ROOT / "docs" / "PRD.md"
AGENT_CONTEXT = REPO_ROOT / "CLAUDE.md"

_PRD_ROW = re.compile(r"^\| \*\*(\w+)\*\* \| ([^|]+?) \| ([^|]+?) \| (\w+) \|$", re.MULTILINE)
_COPY_ROW = re.compile(r"^\| \*\*(\w+)\*\* \| ([^|]+?) \| (\w+) \|$", re.MULTILINE)


def _section(path: Path, start: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    return text[text.index(start) : text.index(end)]


def prd_roster() -> dict[str, tuple[str, str]]:
    """Guide name -> (in scope, status), from PRD §6."""
    section = _section(PRD, "## 6.", "## 7")
    return {name: (scope.strip(), status) for name, _role, scope, status in _PRD_ROW.findall(section)}


def agent_context_roster() -> dict[str, tuple[str, str]]:
    """Guide name -> (in scope, status), from CLAUDE.md's copy of the same table."""
    section = _section(AGENT_CONTEXT, "## The guide network", "## Backlog awareness")
    return {name: (scope.strip(), status) for name, scope, status in _COPY_ROW.findall(section)}


def test_both_tables_are_readable():
    """A parse failure here means one of the tables changed shape, not that it is empty."""
    assert len(prd_roster()) >= 12
    assert len(agent_context_roster()) >= 12


def test_the_agent_context_table_matches_the_prd():
    assert agent_context_roster() == prd_roster()


def test_every_guide_the_schema_knows_about_is_live_in_the_prd():
    roster = prd_roster()
    for guide in GuideId:
        name = guide.value.capitalize()
        assert name in roster, f"{name} is in the schema's GuideId but not in PRD §6"
        assert roster[name][1] == "Live", f"{name} is in the schema's GuideId but is not Live"


@pytest.mark.parametrize("guide", sorted(g.value for g in GuideId))
def test_no_concept_is_scoped_to_a_guide_that_is_not_live(guide):
    """A concept marked for a planned guide would promise scope that cannot answer."""
    roster = prd_roster()
    register = loading.load_register()
    scoped = [c.id for c in register.concepts if guide in [loading.enum_value(g) for g in c.in_scope_of]]
    if scoped:
        assert roster[guide.capitalize()][1] == "Live"


def test_the_register_covers_ilmarinens_domain_and_says_so():
    """This edition is Ilmarinen's; the others extend it rather than replace it."""
    register = loading.load_register()
    counts: dict[str, int] = {}
    for concept in register.concepts:
        for guide in concept.in_scope_of:
            name = loading.enum_value(guide)
            counts[name] = counts.get(name, 0) + 1
    assert max(counts, key=lambda name: counts[name]) == "ilmarinen"
