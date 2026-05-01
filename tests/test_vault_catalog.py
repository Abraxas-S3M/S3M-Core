"""Unit tests for src.vault.catalog VaultCatalog synchronization flows."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from src.vault.catalog import VaultCatalog


class _StubR2Client:
    def __init__(self, files: list[dict[str, object]]) -> None:
        self._files = files

    def list_files(self, prefix: str = "") -> list[dict[str, object]]:
        if prefix:
            return [entry for entry in self._files if str(entry.get("key", "")).startswith(prefix)]
        return list(self._files)

    def set_files(self, files: list[dict[str, object]]) -> None:
        self._files = files


def _entry(key: str, size: int = 0, last_modified: str = "2026-05-01T00:00:00+00:00") -> dict[str, object]:
    return {"key": key, "size": size, "last_modified": last_modified}


def test_sync_adds_and_marks_removed_and_reports_unchanged() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    r2 = _StubR2Client(
        [
            _entry("datasets/alpha/scenario-1/file-a.json", 10),
            _entry("datasets/alpha/scenario-2/file-b.json", 20),
        ]
    )
    catalog = VaultCatalog(r2_client=r2, db_conn=conn)

    first = catalog.sync()
    assert first == {"added": 2, "removed": 0, "unchanged": 0}

    second = catalog.sync()
    assert second == {"added": 0, "removed": 0, "unchanged": 2}

    r2.set_files([_entry("datasets/alpha/scenario-2/file-b.json", 20)])
    third = catalog.sync()
    assert third == {"added": 0, "removed": 1, "unchanged": 1}

    removed_row = conn.execute(
        "SELECT status, is_deleted FROM vault_catalog WHERE r2_key=?;",
        ("datasets/alpha/scenario-1/file-a.json",),
    ).fetchone()
    assert removed_row is not None
    assert str(removed_row["status"]) == "deleted"
    assert int(removed_row["is_deleted"]) == 1


def test_find_by_track_and_scenario_and_unprocessed() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    r2 = _StubR2Client(
        [
            _entry("datasets/bravo/scenario-x/file-1.parquet", 100),
            _entry("datasets/bravo/scenario-y/file-2.parquet", 120),
            _entry("datasets/charlie/scenario-z/file-3.parquet", 140),
        ]
    )
    catalog = VaultCatalog(r2_client=r2, db_conn=conn)
    catalog.sync()

    by_track = catalog.find_by_track("bravo")
    assert len(by_track) == 2
    assert {item["scenario"] for item in by_track} == {"scenario-x", "scenario-y"}

    by_scenario = catalog.find_by_scenario("bravo", "scenario-y")
    assert len(by_scenario) == 1
    assert by_scenario[0]["r2_key"].endswith("file-2.parquet")

    pending = catalog.find_unprocessed()
    assert len(pending) == 3
    assert all(item["status"] == "pending" for item in pending)


def test_mark_processing_and_mark_complete() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    key = "datasets/delta/scenario-a/sample.bin"
    r2 = _StubR2Client([_entry(key, 30)])
    catalog = VaultCatalog(r2_client=r2, db_conn=conn)
    catalog.sync()

    catalog.mark_processing(key)
    processing_status = conn.execute(
        "SELECT status FROM vault_catalog WHERE r2_key=?;",
        (key,),
    ).fetchone()
    assert processing_status is not None
    assert str(processing_status["status"]) == "processing"

    catalog.mark_complete(key)
    complete_status = conn.execute(
        "SELECT status FROM vault_catalog WHERE r2_key=?;",
        (key,),
    ).fetchone()
    assert complete_status is not None
    assert str(complete_status["status"]) == "complete"


def test_get_stats_returns_expected_shape_and_values() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    last_modified = datetime(2026, 5, 1, tzinfo=timezone.utc).isoformat()
    files = [
        _entry("datasets/echo/scenario-a/file-1.bin", 1024, last_modified),
        _entry("datasets/echo/scenario-b/file-2.bin", 2048, last_modified),
        _entry("datasets/foxtrot/scenario-c/file-3.bin", 3072, last_modified),
    ]
    r2 = _StubR2Client(files)
    catalog = VaultCatalog(r2_client=r2, db_conn=conn)
    catalog.sync()
    catalog.mark_complete("datasets/echo/scenario-a/file-1.bin")
    catalog.mark_processing("datasets/echo/scenario-b/file-2.bin")

    stats = catalog.get_stats()
    assert stats["total_files"] == 3
    assert isinstance(stats["total_size_gb"], float)
    assert stats["by_track"] == {"echo": 2, "foxtrot": 1}
    assert stats["by_status"] == {"complete": 1, "pending": 1, "processing": 1}
    assert isinstance(stats["last_sync"], str)
    assert stats["last_sync"]
