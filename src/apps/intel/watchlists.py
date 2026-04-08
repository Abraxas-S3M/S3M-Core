"""SQLite-backed tactical watchlist store with local STIX import/export."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Any
from uuid import uuid4

from src.apps.intel.stix_processor import STIXProcessor


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperationalStore:
    """Lightweight SQLite store for offline operational watchlist persistence."""

    def __init__(self, db_path: str = "data/intel/watchlists.db") -> None:
        self.db_path = db_path
        parent = Path(db_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class WatchlistStore:
    """Persist and exchange watchlists for tactical surveillance triage."""

    _CATEGORY_MAP = {
        "person": "persons",
        "persons": "persons",
        "org": "organizations",
        "orgs": "organizations",
        "organization": "organizations",
        "organizations": "organizations",
        "vessel": "vessels",
        "vessels": "vessels",
        "vehicle": "vehicles",
        "vehicles": "vehicles",
        "site": "sites",
        "sites": "sites",
    }

    _TABLES = {
        "persons": "watchlist_persons",
        "organizations": "watchlist_orgs",
        "vessels": "watchlist_vessels",
        "vehicles": "watchlist_vehicles",
        "sites": "watchlist_sites",
    }

    def __init__(
        self,
        store: OperationalStore | None = None,
        db_path: str | None = None,
        stix_processor: STIXProcessor | None = None,
    ) -> None:
        path = db_path or os.getenv("S3M_WATCHLIST_DB_PATH", "data/intel/watchlists.db")
        self._store = store or OperationalStore(path)
        self._stix = stix_processor or STIXProcessor()
        self._init_schema()

    def _init_schema(self) -> None:
        for table in self._TABLES.values():
            self._store.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    aliases TEXT NOT NULL DEFAULT '[]',
                    country TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '{{}}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._store.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_name ON {table}(name)")

    @classmethod
    def normalize_category(cls, category: str) -> str:
        key = str(category).strip().lower()
        normalized = cls._CATEGORY_MAP.get(key)
        if not normalized:
            raise ValueError(f"unsupported watchlist category: {category}")
        return normalized

    @classmethod
    def _table_for(cls, category: str) -> str:
        normalized = cls.normalize_category(category)
        return cls._TABLES[normalized]

    @staticmethod
    def _normalize_entity(entity: dict[str, Any], entity_id: str | None = None) -> dict[str, Any]:
        item = dict(entity or {})
        normalized_id = str(entity_id or item.get("id") or f"wl-{uuid4().hex[:10]}").strip()
        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError("watchlist entity name is required")

        aliases = item.get("aliases") or []
        if not isinstance(aliases, list):
            raise ValueError("aliases must be a list of strings")
        cleaned_aliases = [str(alias).strip() for alias in aliases if str(alias).strip()]
        country = str(item.get("country", "")).strip()
        details = item.get("details") or {}
        if not isinstance(details, dict):
            raise ValueError("details must be a dictionary")

        now = _utc_now_iso()
        return {
            "id": normalized_id,
            "name": name,
            "aliases": cleaned_aliases,
            "country": country,
            "details": details,
            "created_at": str(item.get("created_at") or now),
            "updated_at": now,
        }

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "aliases": json.loads(str(row["aliases"])),
            "country": str(row["country"]),
            "details": json.loads(str(row["details"])),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def create_entity(self, category: str, entity: dict[str, Any]) -> dict[str, Any]:
        normalized_category = self.normalize_category(category)
        table = self._table_for(normalized_category)
        normalized = self._normalize_entity(entity)
        self._store.execute(
            f"""
            INSERT INTO {table}(id, name, aliases, country, details, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["id"],
                normalized["name"],
                json.dumps(normalized["aliases"], ensure_ascii=True),
                normalized["country"],
                json.dumps(normalized["details"], ensure_ascii=True),
                normalized["created_at"],
                normalized["updated_at"],
            ),
        )
        normalized["category"] = normalized_category
        return normalized

    def get_entity(self, category: str, entity_id: str) -> dict[str, Any] | None:
        normalized_category = self.normalize_category(category)
        table = self._table_for(normalized_category)
        row = self._store.fetchone(f"SELECT * FROM {table} WHERE id = ?", (str(entity_id),))
        if row is None:
            return None
        entity = self._row_to_entity(row)
        entity["category"] = normalized_category
        return entity

    def list_entities(self, category: str) -> list[dict[str, Any]]:
        normalized_category = self.normalize_category(category)
        table = self._table_for(normalized_category)
        rows = self._store.fetchall(f"SELECT * FROM {table} ORDER BY updated_at DESC", ())
        entities = [self._row_to_entity(row) for row in rows]
        for entity in entities:
            entity["category"] = normalized_category
        return entities

    def update_entity(self, category: str, entity_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_entity(category, entity_id)
        if current is None:
            return None
        merged = dict(current)
        merged.update(updates or {})
        merged["id"] = current["id"]
        merged["created_at"] = current["created_at"]
        normalized = self._normalize_entity(merged, entity_id=current["id"])

        table = self._table_for(category)
        self._store.execute(
            f"""
            UPDATE {table}
            SET name = ?, aliases = ?, country = ?, details = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["name"],
                json.dumps(normalized["aliases"], ensure_ascii=True),
                normalized["country"],
                json.dumps(normalized["details"], ensure_ascii=True),
                normalized["updated_at"],
                normalized["id"],
            ),
        )
        normalized["category"] = self.normalize_category(category)
        normalized["created_at"] = current["created_at"]
        return normalized

    def delete_entity(self, category: str, entity_id: str) -> bool:
        table = self._table_for(category)
        cursor = self._store.execute(f"DELETE FROM {table} WHERE id = ?", (str(entity_id),))
        return int(cursor.rowcount or 0) > 0

    def upsert_entity(self, category: str, entity: dict[str, Any]) -> dict[str, Any]:
        target_id = str(entity.get("id", "")).strip()
        if target_id and self.get_entity(category, target_id) is not None:
            updated = self.update_entity(category, target_id, entity)
            assert updated is not None
            return updated
        return self.create_entity(category, entity)

    # ---- CRUD wrappers per entity type ----
    def create_person(self, entity: dict[str, Any]) -> dict[str, Any]:
        return self.create_entity("persons", entity)

    def get_person(self, entity_id: str) -> dict[str, Any] | None:
        return self.get_entity("persons", entity_id)

    def list_persons(self) -> list[dict[str, Any]]:
        return self.list_entities("persons")

    def update_person(self, entity_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return self.update_entity("persons", entity_id, updates)

    def delete_person(self, entity_id: str) -> bool:
        return self.delete_entity("persons", entity_id)

    def create_org(self, entity: dict[str, Any]) -> dict[str, Any]:
        return self.create_entity("organizations", entity)

    def get_org(self, entity_id: str) -> dict[str, Any] | None:
        return self.get_entity("organizations", entity_id)

    def list_orgs(self) -> list[dict[str, Any]]:
        return self.list_entities("organizations")

    def update_org(self, entity_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return self.update_entity("organizations", entity_id, updates)

    def delete_org(self, entity_id: str) -> bool:
        return self.delete_entity("organizations", entity_id)

    def create_vessel(self, entity: dict[str, Any]) -> dict[str, Any]:
        return self.create_entity("vessels", entity)

    def get_vessel(self, entity_id: str) -> dict[str, Any] | None:
        return self.get_entity("vessels", entity_id)

    def list_vessels(self) -> list[dict[str, Any]]:
        return self.list_entities("vessels")

    def update_vessel(self, entity_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return self.update_entity("vessels", entity_id, updates)

    def delete_vessel(self, entity_id: str) -> bool:
        return self.delete_entity("vessels", entity_id)

    def create_vehicle(self, entity: dict[str, Any]) -> dict[str, Any]:
        return self.create_entity("vehicles", entity)

    def get_vehicle(self, entity_id: str) -> dict[str, Any] | None:
        return self.get_entity("vehicles", entity_id)

    def list_vehicles(self) -> list[dict[str, Any]]:
        return self.list_entities("vehicles")

    def update_vehicle(self, entity_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return self.update_entity("vehicles", entity_id, updates)

    def delete_vehicle(self, entity_id: str) -> bool:
        return self.delete_entity("vehicles", entity_id)

    def create_site(self, entity: dict[str, Any]) -> dict[str, Any]:
        return self.create_entity("sites", entity)

    def get_site(self, entity_id: str) -> dict[str, Any] | None:
        return self.get_entity("sites", entity_id)

    def list_sites(self) -> list[dict[str, Any]]:
        return self.list_entities("sites")

    def update_site(self, entity_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return self.update_entity("sites", entity_id, updates)

    def delete_site(self, entity_id: str) -> bool:
        return self.delete_entity("sites", entity_id)

    def export_stix(self, category: str):
        """Export one watchlist category as a STIX 2.1 bundle."""
        normalized_category = self.normalize_category(category)
        entities = self.list_entities(normalized_category)
        export_entities: list[dict[str, Any]] = []
        for entity in entities:
            payload = dict(entity)
            payload["category"] = normalized_category
            export_entities.append(payload)
        return self._stix.bundle_watchlist(export_entities)

    def import_stix(self, bundle: Any) -> int:
        """Ingest STIX entities into local watchlists and return ingested count."""
        imported: list[dict[str, Any]]
        if isinstance(bundle, str) and Path(bundle).exists():
            imported = self._stix.import_bundle(bundle)
        else:
            if hasattr(bundle, "serialize"):
                serialized = str(bundle.serialize())
            elif isinstance(bundle, dict):
                serialized = json.dumps(bundle, ensure_ascii=True)
            elif isinstance(bundle, str):
                serialized = bundle
            else:
                raise ValueError("bundle must be a path, JSON string, dict, or STIX Bundle")

            temp_path: str | None = None
            try:
                with NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as temp_file:
                    temp_file.write(serialized)
                    temp_path = temp_file.name
                imported = self._stix.import_bundle(temp_path)
            finally:
                if temp_path and Path(temp_path).exists():
                    Path(temp_path).unlink()

        ingested = 0
        for entity in imported:
            category = entity.get("category")
            if not category:
                continue
            self.upsert_entity(str(category), entity)
            ingested += 1
        return ingested
