"""Load and filter the approved crisis/escalation resource list (#29, #133).

See ``backend/app/config/crisis_resources.yaml`` for the data and
``docs/specs/crisis-escalation-resources.md`` for how it is governed and
approved. This is the only runtime consumer of that file.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml

logger = logging.getLogger(__name__)

_RESOURCES_PATH: Final[Path] = Path(__file__).resolve().parents[1] / "config" / "crisis_resources.yaml"
_APPROVED_STATUS: Final[str] = "approved"


@dataclass(frozen=True, slots=True)
class CrisisResource:
    """One approved crisis/escalation contact."""

    id: str
    category: str
    name: str
    description: str
    url: str
    phone: str | None
    languages: tuple[str, ...]
    hours: str | None


@dataclass(frozen=True, slots=True)
class CrisisResourceList:
    """The parsed resource file, plus its approval status."""

    version: int
    status: str
    resources: tuple[CrisisResource, ...]

    def by_categories(self, categories: tuple[str, ...]) -> tuple[CrisisResource, ...]:
        """Return resources matching any of the given categories, in file order.

        Args:
            categories: Resource categories to include, e.g. ``("emergency",)``.

        Returns:
            Matching resources, or an empty tuple if ``categories`` is empty.
        """
        if not categories:
            return ()
        wanted = set(categories)
        return tuple(resource for resource in self.resources if resource.category in wanted)


@lru_cache(maxsize=1)
def load_crisis_resources() -> CrisisResourceList:
    """Load and parse the approved crisis/escalation resource list.

    Cached for the process lifetime: the file only changes via a reviewed PR
    (see the governance doc), never at runtime.

    Returns:
        The parsed, immutable resource list.
    """
    with _RESOURCES_PATH.open(encoding="utf-8") as file:
        raw: dict[str, Any] = yaml.safe_load(file)

    status = raw.get("status", "draft")
    if status != _APPROVED_STATUS:
        logger.warning(
            "Crisis/escalation resource list status is %r, not %r — guardrail responses are "
            "surfacing unvetted, draft data. See docs/specs/crisis-escalation-resources.md "
            "and PRD §11 before relying on this for production traffic.",
            status,
            _APPROVED_STATUS,
        )

    resources = tuple(
        CrisisResource(
            id=entry["id"],
            category=entry["category"],
            name=entry["name"],
            description=str(entry["description"]).strip(),
            url=entry["url"],
            phone=entry.get("phone"),
            languages=tuple(entry.get("languages", ())),
            hours=entry.get("hours"),
        )
        for entry in raw.get("resources", ())
    )

    return CrisisResourceList(version=raw.get("version", 1), status=status, resources=resources)
