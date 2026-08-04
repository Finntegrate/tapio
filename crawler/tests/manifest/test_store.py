"""Tests for the SQLite-backed URL manifest store."""

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tapio_crawler.manifest.models import ManifestRecord
from tapio_crawler.manifest.store import ManifestStore


def _record(**overrides: object) -> ManifestRecord:
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
    manifest_store = ManifestStore(tmp_path / "manifest.db")
    yield manifest_store
    manifest_store.close()


def test_upsert_persists_a_new_record(store: ManifestStore) -> None:
    store.upsert(_record())

    found = store.get("migri", "https://migri.fi/en/page")

    assert found is not None
    assert found.discovery_source == {"sitemap"}


def test_upsert_merges_discovery_source_provenance(store: ManifestStore) -> None:
    store.upsert(_record(discovery_source={"sitemap"}))
    store.upsert(_record(discovery_source={"deep_crawl"}))

    found = store.get("migri", "https://migri.fi/en/page")

    assert found is not None
    assert found.discovery_source == {"sitemap", "deep_crawl"}


def test_upsert_advances_last_seen_at_without_duplicating_rows(
    store: ManifestStore,
) -> None:
    later = datetime(2026, 8, 5, tzinfo=UTC)
    store.upsert(_record())
    store.upsert(_record(last_seen_at=later))

    records = store.list_by_site("migri")

    assert len(records) == 1
    assert records[0].last_seen_at == later


def test_upsert_keeps_later_last_seen_at_when_replayed_out_of_order(
    store: ManifestStore,
) -> None:
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
    lastmod = datetime(2026, 1, 1, tzinfo=UTC)
    store.upsert(_record(sitemap_lastmod=lastmod))
    store.upsert(_record(sitemap_lastmod=None))

    found = store.get("migri", "https://migri.fi/en/page")

    assert found is not None
    assert found.sitemap_lastmod == lastmod


def test_list_by_site_filters_by_scope_status(store: ManifestStore) -> None:
    store.upsert(
        _record(canonical_url="https://migri.fi/en/a", scope_status="eligible")
    )
    store.upsert(
        _record(canonical_url="https://migri.fi/en/b", scope_status="blocked_robots"),
    )

    eligible = store.list_by_site("migri", scope_status="eligible")

    assert [record.canonical_url for record in eligible] == ["https://migri.fi/en/a"]


def test_records_from_different_sites_are_independent(store: ManifestStore) -> None:
    store.upsert(_record(site_name="migri"))
    store.upsert(_record(site_name="kela"))

    assert len(store.list_by_site("migri")) == 1
    assert len(store.list_by_site("kela")) == 1
