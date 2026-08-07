"""SQLite-backed URL manifest store.

URL identity is ``(site_name, canonical_url)``: upserting merges discovery
provenance and advances ``last_seen_at`` rather than creating a duplicate row.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
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
    "retry_count",
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

_INTEGER_COLUMNS = frozenset({"content_length", "retry_count"})

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS manifest (
    {", ".join(f"{name} INTEGER" if name in _INTEGER_COLUMNS else f"{name} TEXT" for name in _COLUMNS)},
    PRIMARY KEY (site_name, canonical_url)
);
"""

_DISCOVERY_RUN_SCHEMA = """
CREATE TABLE IF NOT EXISTS discovery_run (
    site_name TEXT PRIMARY KEY,
    completed_at TEXT NOT NULL,
    complete INTEGER NOT NULL,
    config_fingerprint TEXT NOT NULL DEFAULT ''
);
"""


@dataclass
class LastDiscoveryRun:
    """When a site's discovery last completed, for a ``cache_ttl_hours`` check.

    Recorded for every discovery attempt, including incomplete ones - see
    ``get_last_discovery_run``.

    Attributes:
        completed_at: When this run finished (or was marked incomplete).
        complete: Whether this run finished without a fatal interruption.
        config_fingerprint: Hash of the discovery/scope config in effect for
            this run, used to detect config changes that should invalidate
            an otherwise-fresh cache hit. Empty for runs recorded before
            this field was introduced.
    """

    completed_at: datetime
    complete: bool
    config_fingerprint: str = ""


class ManifestStore:
    """Durable, queryable inventory of every discovered source URL.

    Attributes:
        path: Filesystem path to the SQLite database backing this store.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        """Open (creating if needed) the manifest database at ``path``.

        Args:
            path: Location of the SQLite database file. Defaults to
                ``DEFAULT_MANIFEST_PATH`` when omitted.
        """
        self.path = Path(path) if path is not None else Path(DEFAULT_MANIFEST_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # WAL lets one writer and multiple readers proceed concurrently
        # instead of blocking on the default rollback journal; busy_timeout
        # makes a writer wait out a momentary lock instead of raising
        # "database is locked" immediately. Both matter once discovery/render
        # runs for different sites open this same file concurrently (#79).
        self._connection = sqlite3.connect(self.path, timeout=30.0)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=30000")
        self._connection.execute(_SCHEMA)
        self._connection.execute(_DISCOVERY_RUN_SCHEMA)
        self._add_missing_columns()
        self._add_missing_discovery_run_columns()
        self._connection.commit()

    def _add_missing_columns(self) -> None:
        """Add any missing column, so an older database file doesn't fail.

        Compares ``_COLUMNS`` against the database's actual columns and adds
        whatever is missing, so opening a file created by an older schema
        version doesn't fail on the first read/write that touches a newer
        column.
        """
        existing = {row["name"] for row in self._connection.execute("PRAGMA table_info(manifest)")}
        for name in _COLUMNS:
            if name in existing:
                continue
            # Column names are drawn from the fixed _COLUMNS tuple, never
            # from user input, so this isn't a SQL-injection vector.
            if name in _INTEGER_COLUMNS:
                self._connection.execute(f"ALTER TABLE manifest ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            else:
                self._connection.execute(f"ALTER TABLE manifest ADD COLUMN {name} TEXT")

    def _add_missing_discovery_run_columns(self) -> None:
        """Add ``config_fingerprint`` to a ``discovery_run`` table that predates it."""
        existing = {row["name"] for row in self._connection.execute("PRAGMA table_info(discovery_run)")}
        if "config_fingerprint" not in existing:
            self._connection.execute("ALTER TABLE discovery_run ADD COLUMN config_fingerprint TEXT NOT NULL DEFAULT ''")

    def close(self) -> None:
        """Release the underlying SQLite connection."""
        self._connection.close()

    def record_discovery_run(
        self,
        site_name: str,
        completed_at: datetime,
        *,
        complete: bool,
        config_fingerprint: str = "",
    ) -> None:
        """Record that a discovery run finished for ``site_name``.

        Used by ``discovery.cache_ttl_hours`` to decide whether a later
        ``discover`` run can reuse this run's manifest state instead of
        re-fetching.

        Args:
            site_name: Name of the configured source site.
            completed_at: When the run finished.
            complete: Whether the run finished without a fatal interruption.
            config_fingerprint: Hash of the discovery/scope settings this run
                used, so a later run can tell whether the site's
                configuration has changed since and treat a cache hit as
                stale even within ``cache_ttl_hours``.
        """
        self._connection.execute(
            "INSERT INTO discovery_run (site_name, completed_at, complete, config_fingerprint) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (site_name) DO UPDATE SET completed_at = excluded.completed_at, "
            "complete = excluded.complete, config_fingerprint = excluded.config_fingerprint",
            (site_name, completed_at.isoformat(), int(complete), config_fingerprint),
        )
        self._connection.commit()

    def get_last_discovery_run(self, site_name: str) -> LastDiscoveryRun | None:
        """Return when ``site_name``'s discovery last completed, if ever.

        Args:
            site_name: Name of the configured source site.

        Returns:
            The most recently recorded run, including an incomplete one, or
            ``None`` if no run has ever been recorded for this site.
        """
        row = self._connection.execute(
            "SELECT completed_at, complete, config_fingerprint FROM discovery_run WHERE site_name = ?",
            (site_name,),
        ).fetchone()
        if row is None:
            return None
        return LastDiscoveryRun(
            completed_at=datetime.fromisoformat(row["completed_at"]),
            complete=bool(row["complete"]),
            config_fingerprint=row["config_fingerprint"] or "",
        )

    def upsert(self, record: ManifestRecord) -> ManifestRecord:
        """Insert or merge ``record`` by its ``(site_name, canonical_url)`` identity.

        Args:
            record: The candidate record to persist. If a record already
                exists for the same identity, discovery provenance and
                ``last_seen_at``/``sitemap_lastmod`` are merged into it
                rather than overwriting it outright.

        Returns:
            The record as persisted, after any merge with an existing row.
        """
        existing = self.get(record.site_name, record.canonical_url)
        merged = (
            record
            if existing is None
            else existing.model_copy(
                update={
                    "source_url": record.source_url,
                    "discovery_source": existing.discovery_source | record.discovery_source,
                    "sitemap_lastmod": record.sitemap_lastmod or existing.sitemap_lastmod,
                    "last_seen_at": max(record.last_seen_at, existing.last_seen_at),
                    "scope_status": record.scope_status,
                    "scope_reason": record.scope_reason,
                },
            )
        )
        self._write(merged)
        return merged

    def get(self, site_name: str, canonical_url: str) -> ManifestRecord | None:
        """Return the manifest record for one canonical identity, if present.

        Args:
            site_name: Name of the configured source site.
            canonical_url: Canonicalized URL identifying the record.

        Returns:
            The matching record, or ``None`` if no row exists for the identity.
        """
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
        """Return every manifest record for one site, optionally filtered.

        Args:
            site_name: Name of the configured source site.
            scope_status: When given, only return records with this
                ``scope_status`` value.

        Returns:
            The matching records, in no particular order.
        """
        query = "SELECT * FROM manifest WHERE site_name = ?"
        params: list[object] = [site_name]
        if scope_status is not None:
            query += " AND scope_status = ?"
            params.append(scope_status)
        rows = self._connection.execute(query, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def count_by_site(
        self,
        site_name: str,
        *,
        scope_status: str | None = None,
        fetch_status: str | None = None,
    ) -> int:
        """Return the number of manifest records for one site, optionally filtered.

        Args:
            site_name: Name of the configured source site.
            scope_status: When given, only count records with this ``scope_status``.
            fetch_status: When given, only count records with this ``fetch_status``.

        Returns:
            The matching row count.
        """
        query = "SELECT COUNT(*) FROM manifest WHERE site_name = ?"
        params: list[object] = [site_name]
        if scope_status is not None:
            query += " AND scope_status = ?"
            params.append(scope_status)
        if fetch_status is not None:
            query += " AND fetch_status = ?"
            params.append(fetch_status)
        row = self._connection.execute(query, params).fetchone()
        return int(row[0])

    def save(self, record: ManifestRecord) -> None:
        """Persist ``record`` verbatim, without ``upsert()``'s discovery-merge policy.

        Args:
            record: The full record to write, already read and mutated by
                the caller (for example, after a render attempt).
        """
        self._write(record)

    def list_eligible_page(
        self,
        site_name: str,
        *,
        after_canonical_url: str = "",
        limit: int = 500,
    ) -> list[ManifestRecord]:
        """Return one keyset-paginated page of a site's eligible records.

        Args:
            site_name: Name of the configured source site.
            after_canonical_url: Return records whose ``canonical_url`` sorts
                strictly after this value. Empty string starts from the
                beginning.
            limit: Maximum number of records to return.

        Returns:
            Up to ``limit`` eligible records, ordered by ``canonical_url``.
        """
        rows = self._connection.execute(
            "SELECT * FROM manifest WHERE site_name = ? AND scope_status = 'eligible' "
            "AND canonical_url > ? ORDER BY canonical_url LIMIT ?",
            (site_name, after_canonical_url, limit),
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def rekey(
        self,
        site_name: str,
        old_canonical_url: str,
        new_record: ManifestRecord,
    ) -> None:
        """Move a record from ``old_canonical_url`` to ``new_record.canonical_url``.

        Used when rendering discovers that a URL's true canonical target
        differs from the one it was discovered under (for example, a
        redirect resolves to a different page). Deletes the old row and
        writes ``new_record``, so exactly one manifest record and one
        artifact ever exist for the resolved page. Callers should carry the
        old row's ``first_seen_at``/``discovery_source`` into ``new_record``
        before calling this.

        If a record already exists under ``new_record.canonical_url`` (two
        different discovered URLs redirecting to the same target, or the
        target having its own discovery history), that existing record's
        provenance is merged in rather than being silently overwritten:
        ``discovery_source`` is unioned and ``first_seen_at``/``last_seen_at``
        keep their earliest/latest values. ``new_record``'s own render-outcome
        fields (``fetch_status``, ``content_hash``, ``last_rendered_at``,
        etc.) always win, since it reflects the render that just happened.

        Args:
            site_name: Name of the configured source site.
            old_canonical_url: The record's previous canonical identity.
            new_record: The record to persist under its new canonical identity.
        """
        existing_target = self.get(site_name, new_record.canonical_url)
        merged = (
            new_record
            if existing_target is None
            else new_record.model_copy(
                update={
                    "discovery_source": existing_target.discovery_source | new_record.discovery_source,
                    "first_seen_at": min(existing_target.first_seen_at, new_record.first_seen_at),
                    "last_seen_at": max(existing_target.last_seen_at, new_record.last_seen_at),
                },
            )
        )
        self._connection.execute(
            "DELETE FROM manifest WHERE site_name = ? AND canonical_url = ?",
            (site_name, old_canonical_url),
        )
        self._write(merged)

    def _write(self, record: ManifestRecord) -> None:
        """Upsert ``record``'s row into the ``manifest`` table.

        Args:
            record: The record to write, already merged with any existing row.
        """
        values = _record_to_row(record)
        column_names = ", ".join(_COLUMNS)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        update_clause = ", ".join(
            f"{name} = excluded.{name}" for name in _COLUMNS if name not in {"site_name", "canonical_url"}
        )
        # Column names are drawn from the fixed _COLUMNS tuple, never from
        # user input, so this isn't a SQL-injection vector.
        self._connection.execute(
            f"INSERT INTO manifest ({column_names}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT (site_name, canonical_url) DO UPDATE SET {update_clause}",
            [values[name] for name in _COLUMNS],
        )
        self._connection.commit()


def _record_to_row(record: ManifestRecord) -> dict[str, Any]:
    """Serialize ``record`` into a JSON-compatible column-name-keyed mapping.

    Args:
        record: The record to serialize.

    Returns:
        A mapping from column name to its SQLite-storable value.
    """
    data = record.model_dump(mode="json")
    data["discovery_source"] = json.dumps(sorted(record.discovery_source))
    return data


def _row_to_record(row: sqlite3.Row) -> ManifestRecord:
    """Deserialize one ``manifest`` table row into a ``ManifestRecord``.

    Args:
        row: The raw SQLite row to deserialize.

    Returns:
        The reconstructed record.
    """
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
