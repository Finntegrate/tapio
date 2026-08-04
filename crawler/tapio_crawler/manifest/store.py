"""SQLite-backed URL manifest store.

URL identity is ``(site_name, canonical_url)``: upserting merges discovery
provenance and advances ``last_seen_at`` rather than creating a duplicate row.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from tapio_crawler.config.settings import DEFAULT_MANIFEST_PATH
from tapio_crawler.manifest.models import ManifestRecord

_COLUMNS = (
    "site_name",
    "canonical_url",
    "source_url",
    "discovery_source",
    "sitemap_lastmod",
    "first_seen_at",
    "last_seen_at",
    "scope_status",
    "scope_reason",
    "fetch_status",
    "last_attempt_at",
    "retry_after",
    "content_hash",
    "content_length",
    "title",
    "language",
    "last_rendered_at",
    "last_ingested_at",
    "extractor_version",
    "cache_status",
    "validation_status",
)

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS manifest (
    {", ".join(f"{name} TEXT" if name != "content_length" else f"{name} INTEGER" for name in _COLUMNS)},
    PRIMARY KEY (site_name, canonical_url)
);
"""


class ManifestStore:
    """Durable, queryable inventory of every discovered source URL."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else Path(DEFAULT_MANIFEST_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(_SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        """Release the underlying SQLite connection."""
        self._connection.close()

    def upsert(self, record: ManifestRecord) -> ManifestRecord:
        """Insert or merge ``record`` by its ``(site_name, canonical_url)`` identity."""
        existing = self.get(record.site_name, record.canonical_url)
        merged = (
            record
            if existing is None
            else existing.model_copy(
                update={
                    "source_url": record.source_url,
                    "discovery_source": existing.discovery_source
                    | record.discovery_source,
                    "sitemap_lastmod": record.sitemap_lastmod
                    or existing.sitemap_lastmod,
                    "last_seen_at": max(record.last_seen_at, existing.last_seen_at),
                    "scope_status": record.scope_status,
                    "scope_reason": record.scope_reason,
                },
            )
        )
        self._write(merged)
        return merged

    def get(self, site_name: str, canonical_url: str) -> ManifestRecord | None:
        """Return the manifest record for one canonical identity, if present."""
        row = self._connection.execute(
            "SELECT * FROM manifest WHERE site_name = ? AND canonical_url = ?",
            (site_name, canonical_url),
        ).fetchone()
        return None if row is None else _row_to_record(row)

    def list_by_site(
        self,
        site_name: str,
        *,
        scope_status: str | None = None,
    ) -> list[ManifestRecord]:
        """Return every manifest record for one site, optionally filtered."""
        query = "SELECT * FROM manifest WHERE site_name = ?"
        params: list[object] = [site_name]
        if scope_status is not None:
            query += " AND scope_status = ?"
            params.append(scope_status)
        rows = self._connection.execute(query, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def _write(self, record: ManifestRecord) -> None:
        values = _record_to_row(record)
        column_names = ", ".join(_COLUMNS)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        update_clause = ", ".join(
            f"{name} = excluded.{name}"
            for name in _COLUMNS
            if name not in {"site_name", "canonical_url"}
        )
        self._connection.execute(
            f"INSERT INTO manifest ({column_names}) VALUES ({placeholders}) "
            f"ON CONFLICT (site_name, canonical_url) DO UPDATE SET {update_clause}",
            [values[name] for name in _COLUMNS],
        )
        self._connection.commit()


def _record_to_row(record: ManifestRecord) -> dict[str, Any]:
    data = record.model_dump(mode="json")
    data["discovery_source"] = json.dumps(sorted(record.discovery_source))
    return data


def _row_to_record(row: sqlite3.Row) -> ManifestRecord:
    data = dict(row)
    data["discovery_source"] = set(json.loads(data["discovery_source"] or "[]"))
    for field_name in (
        "sitemap_lastmod",
        "first_seen_at",
        "last_seen_at",
        "last_attempt_at",
        "retry_after",
        "last_rendered_at",
        "last_ingested_at",
    ):
        if data.get(field_name):
            data[field_name] = datetime.fromisoformat(data[field_name])
    return ManifestRecord.model_validate(data)
