"""SQLite-backed operational persistence for GUI workspace adapters."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any


TABLE_PRIMARY_KEYS: dict[str, str] = {
    "decisions": "id",
    "threats": "id",
    "tracks": "id",
    "messages": "id",
    "fleet_assets": "unitId",
    "supply_items": "category",
    "readiness_personnel": "unitId",
    "scenarios": "id",
    "incidents": "id",
}


class OperationalStore:
    """Small tactical-state database with table-level JSON persistence."""

    def __init__(self, db_path: str | Path = "data/s3m_operational.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._configure_database()

    def _configure_database(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL;")
            self._connection.execute("PRAGMA synchronous=NORMAL;")

    def _ensure_table(self, table: str) -> str:
        primary_key = TABLE_PRIMARY_KEYS.get(table)
        if primary_key is None:
            raise ValueError(f"unsupported table: {table}")

        with self._lock:
            self._connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{table}" (
                    "{primary_key}" TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._connection.commit()
        return primary_key

    @staticmethod
    def _record_to_dict(record: Any) -> dict[str, Any]:
        if isinstance(record, dict):
            return dict(record)
        if hasattr(record, "model_dump"):
            payload = record.model_dump()
            if isinstance(payload, dict):
                return payload
        if hasattr(record, "to_dict"):
            payload = record.to_dict()
            if isinstance(payload, dict):
                return payload
        return {}

    def upsert(self, table: str, record: Any) -> None:
        primary_key = self._ensure_table(table)
        payload = self._record_to_dict(record)
        if not payload:
            return

        key_value = payload.get(primary_key)
        if key_value is None and primary_key != "id":
            key_value = payload.get("id")
        if key_value is None:
            raise ValueError(f"missing primary key '{primary_key}' for table '{table}'")

        payload_json = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._connection.execute(
                f"""
                INSERT INTO "{table}" ("{primary_key}", payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT("{primary_key}") DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at;
                """,
                (str(key_value), payload_json, timestamp),
            )
            self._connection.commit()

    def get_all(self, table: str) -> list[dict[str, Any]]:
        self._ensure_table(table)
        with self._lock:
            cursor = self._connection.execute(
                f'SELECT payload FROM "{table}" ORDER BY updated_at DESC;'
            )
            rows = cursor.fetchall()

        records: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def query(self, table: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        records = self.get_all(table)
        if not filters:
            return records

        matched: list[dict[str, Any]] = []
        for record in records:
            include = True
            for key, value in filters.items():
                if record.get(key) != value:
                    include = False
                    break
            if include:
                matched.append(record)
        return matched

    def has_data(self, table: str) -> bool:
        self._ensure_table(table)
        with self._lock:
            cursor = self._connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1;')
            return cursor.fetchone() is not None

    def close(self) -> None:
        with self._lock:
            self._connection.close()
