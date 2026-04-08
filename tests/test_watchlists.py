"""Tests for the SQLite-backed surveillance watchlist store."""

from __future__ import annotations

import pytest

pytest.importorskip("stix2")

from src.apps.intel.watchlists import WatchlistStore


def test_watchlist_store_person_crud(tmp_path) -> None:
    store = WatchlistStore(db_path=str(tmp_path / "watchlists.db"))
    created = store.create_person(
        {
            "id": "wl-p-1",
            "name": "Person Alpha",
            "aliases": ["Alpha"],
            "country": "SA",
            "details": {"source": "unit-test"},
        }
    )
    assert created["id"] == "wl-p-1"
    assert created["category"] == "persons"

    fetched = store.get_person("wl-p-1")
    assert fetched is not None
    assert fetched["name"] == "Person Alpha"
    assert fetched["aliases"] == ["Alpha"]

    updated = store.update_person("wl-p-1", {"aliases": ["Alpha", "A1"]})
    assert updated is not None
    assert updated["aliases"] == ["Alpha", "A1"]

    listed = store.list_persons()
    assert len(listed) == 1
    assert listed[0]["id"] == "wl-p-1"

    assert store.delete_person("wl-p-1") is True
    assert store.get_person("wl-p-1") is None


def test_watchlist_store_export_import_stix(tmp_path) -> None:
    source = WatchlistStore(db_path=str(tmp_path / "source.db"))
    target = WatchlistStore(db_path=str(tmp_path / "target.db"))
    source.create_org(
        {
            "id": "wl-o-1",
            "name": "Org Bravo",
            "aliases": ["OB"],
            "country": "SA",
        }
    )

    bundle = source.export_stix("organizations")
    ingested = target.import_stix(bundle)
    assert ingested == 1

    imported_orgs = target.list_orgs()
    assert len(imported_orgs) == 1
    assert imported_orgs[0]["name"] == "Org Bravo"
