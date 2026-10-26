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


def test_get_last_discovery_run_returns_none_when_never_recorded(
    store: ManifestStore,
) -> None:
    """A site with no recorded discovery run has no cached run state (#76)."""
    assert store.get_last_discovery_run("migri") is None


def test_record_discovery_run_can_be_read_back(store: ManifestStore) -> None:
    """A recorded discovery run's completion time and status round-trip (#76)."""
    completed_at = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)

    store.record_discovery_run("migri", completed_at, complete=True)
    last_run = store.get_last_discovery_run("migri")

    assert last_run is not None
    assert last_run.completed_at == completed_at
    assert last_run.complete is True


def test_record_discovery_run_overwrites_the_prior_run_for_a_site(
    store: ManifestStore,
) -> None:
    """Recording a new discovery run replaces the site's previous run state,
    rather than accumulating a history (#76).
    """
    earlier = datetime(2026, 8, 3, tzinfo=UTC)
    later = datetime(2026, 8, 5, tzinfo=UTC)
    store.record_discovery_run("migri", earlier, complete=False)

    store.record_discovery_run("migri", later, complete=True)
    last_run = store.get_last_discovery_run("migri")

    assert last_run is not None
    assert last_run.completed_at == later
    assert last_run.complete is True


def test_record_discovery_run_is_independent_per_site(store: ManifestStore) -> None:
    """Recording a run for one site does not affect another site's state (#76)."""
    completed_at = datetime(2026, 8, 4, tzinfo=UTC)
    store.record_discovery_run("migri", completed_at, complete=True)

    assert store.get_last_discovery_run("kela") is None


def test_list_retryable_page_returns_failed_eligible_records(store: ManifestStore) -> None:
    """Only eligible records whose last fetch failed are retryable by default."""
    store.upsert(_record(canonical_url="https://migri.fi/a", source_url="https://migri.fi/a", fetch_status="failed"))
    store.upsert(_record(canonical_url="https://migri.fi/b", source_url="https://migri.fi/b", fetch_status="success"))
    store.upsert(
        _record(
            canonical_url="https://migri.fi/c",
            source_url="https://migri.fi/c",
            scope_status="inactive_candidate",
        ),
    )

    page = store.list_retryable_page("migri")

    assert [record.canonical_url for record in page] == ["https://migri.fi/a"]


def test_list_retryable_page_can_include_inactive_candidates_and_paginates(store: ManifestStore) -> None:
    """``include_inactive`` adds inactive candidates, and the keyset cursor pages through them."""
    store.upsert(_record(canonical_url="https://migri.fi/a", source_url="https://migri.fi/a", fetch_status="failed"))
    store.upsert(
        _record(
            canonical_url="https://migri.fi/c",
            source_url="https://migri.fi/c",
            scope_status="inactive_candidate",
        ),
    )

    first = store.list_retryable_page("migri", limit=1, include_inactive=True)
    second = store.list_retryable_page(
        "migri",
        after_canonical_url=first[0].canonical_url,
        limit=1,
        include_inactive=True,
    )

    assert [r.canonical_url for r in first + second] == ["https://migri.fi/a", "https://migri.fi/c"]


class _FlakyConnection:
    """Wraps a real connection; raises ``error`` on the first ``failures`` matching statements."""

    def __init__(self, real: sqlite3.Connection, *, failures: int, match: str, error: str) -> None:
        self._real = real
        self._remaining = failures
        self._match = match
        self._error = error
        self.attempts = 0

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        if self._match in sql:
            self.attempts += 1
            if self._remaining > 0:
                self._remaining -= 1
                raise sqlite3.OperationalError(self._error)
        return self._real.execute(sql, *args)

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def _flaky(store: ManifestStore, *, failures: int, match: str, error: str = "database is locked") -> _FlakyConnection:
    flaky = _FlakyConnection(store._connection, failures=failures, match=match, error=error)
    store._connection = flaky  # type: ignore[assignment]
    return flaky


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record retry waits instead of sleeping through them."""
    waits: list[float] = []
    monkeypatch.setattr("tapio_crawler.manifest.store.time.sleep", waits.append)
    return waits


def test_a_write_that_hits_a_transient_lock_is_retried(store: ManifestStore, no_sleep: list[float]) -> None:
    flaky = _flaky(store, failures=2, match="INSERT INTO manifest")

    store.upsert(_record())

    assert flaky.attempts == 3
    assert no_sleep == [0.5, 1.0]
    assert store.get("migri", _record().canonical_url) is not None


def test_a_lock_that_outlasts_every_retry_is_raised(store: ManifestStore, no_sleep: list[float]) -> None:
    flaky = _flaky(store, failures=10, match="INSERT INTO discovery_run")

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        store.record_discovery_run("migri", datetime.now(UTC), complete=True)

    assert flaky.attempts == 4  # one try plus three retries
    assert no_sleep == [0.5, 1.0, 2.0]


def test_other_operational_errors_are_not_retried(store: ManifestStore, no_sleep: list[float]) -> None:
    flaky = _flaky(store, failures=1, match="INSERT INTO manifest", error="disk I/O error")

    with pytest.raises(sqlite3.OperationalError, match="disk I/O"):
        store.save(_record())

    assert flaky.attempts == 1
    assert no_sleep == []


def test_a_rekey_that_never_gets_the_lock_leaves_the_old_row_in_place(
    store: ManifestStore, no_sleep: list[float]
) -> None:
    """The delete and insert are one unit: a failed rekey must not lose the record."""
    old = _record()
    store.upsert(old)
    new = _record(canonical_url="https://migri.fi/en/moved")
    _flaky(store, failures=10, match="INSERT INTO manifest")

    with pytest.raises(sqlite3.OperationalError):
        store.rekey("migri", old.canonical_url, new)

    assert store.get("migri", old.canonical_url) is not None
    assert store.get("migri", new.canonical_url) is None


def test_a_deep_crawl_checkpoint_round_trips(store: ManifestStore) -> None:
    state = {"seeds": {"https://example.com": {"visited": ["a"], "pending": []}}, "discovered": ["a"]}

    store.save_deep_crawl_checkpoint("migri", "fp-1", state)

    assert store.get_deep_crawl_checkpoint("migri", "fp-1") == state


def test_a_checkpoint_saved_under_other_settings_is_discarded(store: ManifestStore) -> None:
    store.save_deep_crawl_checkpoint("migri", "fp-old", {"discovered": ["a"]})

    assert store.get_deep_crawl_checkpoint("migri", "fp-new") is None
    assert store.get_deep_crawl_checkpoint("migri", "fp-old") is None  # deleted, not just skipped


def test_clearing_a_checkpoint_removes_it(store: ManifestStore) -> None:
    store.save_deep_crawl_checkpoint("migri", "fp-1", {"discovered": []})

    store.clear_deep_crawl_checkpoint("migri")

    assert store.get_deep_crawl_checkpoint("migri", "fp-1") is None
