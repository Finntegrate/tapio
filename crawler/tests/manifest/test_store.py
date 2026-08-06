"""Tests for the SQLite-backed URL manifest store."""

import sqlite3
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tapio_crawler.manifest.models import ManifestRecord
from tapio_crawler.manifest.store import _COLUMNS, ManifestStore


def _record(**overrides: object) -> ManifestRecord:
    """Build a minimal valid ``ManifestRecord``, overriding any given fields.

    Args:
        **overrides: Field values to override on top of the defaults.

    Returns:
        The constructed record.
    """
    now = datetime(2026, 8, 4, tzinfo=UTC)
    defaults: dict[str, object] = {
        "site_name": "migri",
        "source_url": "https://migri.fi/en/page",
        "canonical_url": "https://migri.fi/en/page",
        "discovery_source": {"sitemap"},
        "first_seen_at": now,
        "last_seen_at": now,
        "scope_status": "eligible",
    }
    defaults.update(overrides)
    return ManifestRecord(**defaults)


@pytest.fixture
def store(tmp_path: Path) -> Generator[ManifestStore]:
    """Yield a ``ManifestStore`` backed by a temporary database file."""
    manifest_store = ManifestStore(tmp_path / "manifest.db")
    yield manifest_store
    manifest_store.close()


def test_upsert_persists_a_new_record(store: ManifestStore) -> None:
    """A first upsert for an identity persists it and it can be read back."""
    store.upsert(_record())

    found = store.get("migri", "https://migri.fi/en/page")

    assert found is not None
    assert found.discovery_source == {"sitemap"}


def test_upsert_merges_discovery_source_provenance(store: ManifestStore) -> None:
    """Upserting the same identity accumulates discovery sources rather than
    replacing them.
    """
    store.upsert(_record(discovery_source={"sitemap"}))
    store.upsert(_record(discovery_source={"deep_crawl"}))

    found = store.get("migri", "https://migri.fi/en/page")

    assert found is not None
    assert found.discovery_source == {"sitemap", "deep_crawl"}


def test_upsert_advances_last_seen_at_without_duplicating_rows(
    store: ManifestStore,
) -> None:
    """Re-upserting the same identity updates ``last_seen_at`` in place
    instead of creating a second row.
    """
    later = datetime(2026, 8, 5, tzinfo=UTC)
    store.upsert(_record())
    store.upsert(_record(last_seen_at=later))

    records = store.list_by_site("migri")

    assert len(records) == 1
    assert records[0].last_seen_at == later


def test_upsert_keeps_later_last_seen_at_when_replayed_out_of_order(
    store: ManifestStore,
) -> None:
    """Upserting an older ``last_seen_at`` after a newer one does not
    regress the stored value.
    """
    earlier = datetime(2026, 8, 3, tzinfo=UTC)
    later = datetime(2026, 8, 5, tzinfo=UTC)
    store.upsert(_record(last_seen_at=later))
    store.upsert(_record(last_seen_at=earlier))

    found = store.get("migri", "https://migri.fi/en/page")

    assert found is not None
    assert found.last_seen_at == later


def test_upsert_keeps_earlier_sitemap_lastmod_when_not_resupplied(
    store: ManifestStore,
) -> None:
    """An upsert without a ``sitemap_lastmod`` value does not clear a
    previously recorded one.
    """
    lastmod = datetime(2026, 1, 1, tzinfo=UTC)
    store.upsert(_record(sitemap_lastmod=lastmod))
    store.upsert(_record(sitemap_lastmod=None))

    found = store.get("migri", "https://migri.fi/en/page")

    assert found is not None
    assert found.sitemap_lastmod == lastmod


def test_list_by_site_filters_by_scope_status(store: ManifestStore) -> None:
    """``list_by_site`` with ``scope_status`` returns only matching records."""
    store.upsert(_record(canonical_url="https://migri.fi/en/a", scope_status="eligible"))
    store.upsert(
        _record(canonical_url="https://migri.fi/en/b", scope_status="blocked_robots"),
    )

    eligible = store.list_by_site("migri", scope_status="eligible")

    assert [record.canonical_url for record in eligible] == ["https://migri.fi/en/a"]


def test_records_from_different_sites_are_independent(store: ManifestStore) -> None:
    """Records for different sites do not collide even with the same URL."""
    store.upsert(_record(site_name="migri"))
    store.upsert(_record(site_name="kela"))

    assert len(store.list_by_site("migri")) == 1
    assert len(store.list_by_site("kela")) == 1


def test_list_eligible_page_paginates_in_canonical_url_order(store: ManifestStore) -> None:
    """Paging through eligible records with a small ``limit`` covers every
    record exactly once, in ``canonical_url`` order.
    """
    for letter in "cab":
        store.upsert(_record(canonical_url=f"https://migri.fi/en/{letter}"))
    store.upsert(_record(canonical_url="https://migri.fi/en/d", scope_status="excluded"))

    first_page = store.list_eligible_page("migri", limit=2)
    second_page = store.list_eligible_page(
        "migri",
        after_canonical_url=first_page[-1].canonical_url,
        limit=2,
    )

    assert [r.canonical_url for r in first_page] == ["https://migri.fi/en/a", "https://migri.fi/en/b"]
    assert [r.canonical_url for r in second_page] == ["https://migri.fi/en/c"]


def test_save_writes_a_record_verbatim_without_merge(store: ManifestStore) -> None:
    """``save`` persists exactly the given record, unlike ``upsert``'s merge policy."""
    store.upsert(_record(discovery_source={"sitemap"}, fetch_status=None))

    store.save(_record(discovery_source=set(), fetch_status="success"))

    found = store.get("migri", "https://migri.fi/en/page")
    assert found is not None
    assert found.discovery_source == set()
    assert found.fetch_status == "success"


def test_rekey_moves_a_record_to_a_new_canonical_identity(store: ManifestStore) -> None:
    """``rekey`` deletes the old row and writes the record under its new identity."""
    store.upsert(_record(canonical_url="https://migri.fi/en/old"))

    store.rekey(
        "migri",
        "https://migri.fi/en/old",
        _record(canonical_url="https://migri.fi/en/new", fetch_status="success"),
    )

    assert store.get("migri", "https://migri.fi/en/old") is None
    moved = store.get("migri", "https://migri.fi/en/new")
    assert moved is not None
    assert moved.fetch_status == "success"


def test_rekey_merges_provenance_with_an_existing_target_record(store: ManifestStore) -> None:
    """``rekey`` merges discovery provenance instead of overwriting an
    already-existing record at the new canonical identity.
    """
    earlier = datetime(2026, 1, 1, tzinfo=UTC)
    store.upsert(
        _record(
            canonical_url="https://migri.fi/en/target",
            discovery_source={"sitemap"},
            first_seen_at=earlier,
            last_seen_at=earlier,
        ),
    )
    store.upsert(_record(canonical_url="https://migri.fi/en/old"))

    store.rekey(
        "migri",
        "https://migri.fi/en/old",
        _record(
            canonical_url="https://migri.fi/en/target",
            discovery_source={"deep_crawl"},
            fetch_status="success",
        ),
    )

    assert store.get("migri", "https://migri.fi/en/old") is None
    merged = store.get("migri", "https://migri.fi/en/target")
    assert merged is not None
    assert merged.discovery_source == {"sitemap", "deep_crawl"}
    assert merged.first_seen_at == earlier
    assert merged.fetch_status == "success"


def test_opening_a_pre_migration_database_adds_missing_columns(tmp_path: Path) -> None:
    """A manifest.db written before ``retry_count`` existed gains the column
    on open, rather than every subsequent write failing with a SQLite
    "no such column" error.
    """
    db_path = tmp_path / "legacy.db"
    legacy_columns = [name for name in _COLUMNS if name != "retry_count"]
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            f"CREATE TABLE manifest ({', '.join(f'{name} TEXT' for name in legacy_columns)}, "
            "PRIMARY KEY (site_name, canonical_url))",
        )
        connection.commit()
    finally:
        connection.close()

    manifest_store = ManifestStore(db_path)
    try:
        manifest_store.save(_record(retry_count=3))
        found = manifest_store.get("migri", "https://migri.fi/en/page")
    finally:
        manifest_store.close()

    assert found is not None
    assert found.retry_count == 3


def test_count_by_site_filters_by_scope_and_fetch_status(store: ManifestStore) -> None:
    """``count_by_site`` counts only records matching the given filters."""
    store.upsert(_record(canonical_url="https://migri.fi/en/a", fetch_status="success"))
    store.upsert(_record(canonical_url="https://migri.fi/en/b", fetch_status="failed"))
    store.upsert(_record(canonical_url="https://migri.fi/en/c", scope_status="excluded"))

    assert store.count_by_site("migri", scope_status="eligible") == 2
    assert store.count_by_site("migri", scope_status="eligible", fetch_status="success") == 1


def test_uses_wal_journal_mode(store: ManifestStore) -> None:
    """The store opens with WAL journal mode, so concurrent per-site crawl
    processes get one-writer/many-readers instead of blocking on the
    default rollback journal (#79).
    """
    mode = store._connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


def test_configures_a_busy_timeout(store: ManifestStore) -> None:
    """The store raises SQLite's busy_timeout above its 5s default, so a
    concurrent writer waits out a momentary lock instead of a per-site
    crawl process immediately raising "database is locked" (#79).
    """
    timeout_ms = store._connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert timeout_ms == 30000
