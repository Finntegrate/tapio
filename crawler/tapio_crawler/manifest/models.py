"""URL manifest record schema.

See docs/specs/crawler-improvements.md, "URL manifest". Fields owned by
later phases (rendering, cache/refresh policy) default to ``None`` until
Phase 2 populates them; discovery only writes the fields it owns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ScopeStatus = Literal[
    "eligible",
    "blocked_robots",
    "out_of_scope",
    "excluded",
    "unsupported_content_type",
]

DiscoverySource = Literal["sitemap", "deep_crawl", "operator"]


class ManifestRecord(BaseModel):
    """One canonical source URL and its discovery/collection state."""

    site_name: str
    source_url: str
    canonical_url: str
    # Accumulates every mechanism that has found this URL; never overwritten.
    discovery_source: set[DiscoverySource] = Field(default_factory=set)
    sitemap_lastmod: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    scope_status: ScopeStatus
    scope_reason: str | None = None
    fetch_status: str | None = None
    last_attempt_at: datetime | None = None
    retry_after: datetime | None = None
    content_hash: str | None = None
    content_length: int | None = None
    title: str | None = None
    language: str | None = None
    last_rendered_at: datetime | None = None
    last_ingested_at: datetime | None = None
    extractor_version: str | None = None
    cache_status: str | None = None
    validation_status: str | None = None
