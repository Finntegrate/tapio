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
    """One canonical source URL and its discovery/collection state.

    Attributes:
        site_name: Name of the configured source site.
        source_url: The URL as originally discovered, before canonicalization.
        canonical_url: Canonicalized form of ``source_url``; part of the
            record's identity together with ``site_name``.
        discovery_source: Every discovery mechanism that has found this URL;
            accumulates over time and is never overwritten.
        sitemap_lastmod: ``<lastmod>`` value from the sitemap, if supplied.
        first_seen_at: Timestamp when this URL was first discovered.
        last_seen_at: Timestamp of the most recent discovery run that saw
            this URL.
        scope_status: Whether the URL is eligible for collection, and if
            not, the category of exclusion.
        scope_reason: Machine-readable reason code backing ``scope_status``.
        fetch_status: Outcome of the most recent fetch attempt, if any.
        last_attempt_at: Timestamp of the most recent fetch attempt.
        retry_after: Earliest time a failed fetch should be retried.
        content_hash: Hash of the fetched content, used to detect changes.
        content_length: Byte length of the fetched content.
        title: Page title extracted from the fetched content.
        language: Detected or configured language of the content.
        last_rendered_at: Timestamp of the most recent rendering pass.
        last_ingested_at: Timestamp of the most recent ingestion into the
            vector store.
        extractor_version: Version identifier of the content extractor used.
        cache_status: Outcome of cache validation for the most recent fetch.
        validation_status: Outcome of content validation checks.
    """

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
