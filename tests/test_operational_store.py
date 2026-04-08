from __future__ import annotations

import pytest

from src.persistence.operational_store import OperationalStore


def test_operational_store_upsert_query_and_get_all(tmp_path) -> None:
    store = OperationalStore(db_path=tmp_path / "ops.db")
    try:
        store.upsert("decisions", {"id": "DEC-1", "status": "pending", "risk_score": 0.42})
        assert store.has_data("decisions") is True

        all_rows = store.get_all("decisions")
        assert len(all_rows) == 1
        assert all_rows[0]["id"] == "DEC-1"
        assert all_rows[0]["status"] == "pending"

        pending_rows = store.query("decisions", {"status": "pending"})
        assert len(pending_rows) == 1

        store.upsert("decisions", {"id": "DEC-1", "status": "approved", "risk_score": 0.42})
        assert store.query("decisions", {"status": "pending"}) == []
        approved_rows = store.query("decisions", {"status": "approved"})
        assert len(approved_rows) == 1
    finally:
        store.close()


def test_operational_store_enables_wal_mode(tmp_path) -> None:
    store = OperationalStore(db_path=tmp_path / "ops.db")
    try:
        row = store._connection.execute("PRAGMA journal_mode;").fetchone()  # noqa: SLF001
        assert row is not None
        assert str(row[0]).lower() == "wal"
    finally:
        store.close()


def test_operational_store_rejects_unknown_tables(tmp_path) -> None:
    store = OperationalStore(db_path=tmp_path / "ops.db")
    try:
        with pytest.raises(ValueError):
            store.get_all("unknown_table")
    finally:
        store.close()
