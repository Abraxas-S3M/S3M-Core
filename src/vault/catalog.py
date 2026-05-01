"""
Vault catalog synchronization and query utilities for S3M-Engine.

Tactical context:
    The training vault inventory is a mission data source. This catalog keeps a
    durable local index of remote objects so operators can identify unprocessed
    datasets and confirm readiness before downstream edge distribution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from src.vault.r2_client import R2Client


class VaultCatalog:
    """Local catalog index synchronized with Cloudflare R2 object inventory."""

    def __init__(self, r2_client: R2Client, db_conn: sqlite3.Connection | None = None) -> None:
        if r2_client is None:
            raise ValueError("r2_client is required")
        self.r2_client = r2_client
        self._owns_connection = db_conn is None
        if db_conn is None:
            db_path = Path("data/vault_catalog.db")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db_conn = db_conn
        self._db_conn.row_factory = sqlite3.Row
        self._ensure_schema()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _required_value(name: str, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} must be non-empty")
        return normalized

    @staticmethod
    def _extract_track_scenario(r2_key: str) -> tuple[str, str]:
        """
        Infer track/scenario labels from vault key path.

        Tactical context:
            Track and scenario labels let analysts prioritize data pipelines by
            operational theater and mission pattern.
        """
        segments = [segment for segment in r2_key.strip("/").split("/") if segment]
        if not segments:
            return "unknown", "unknown"

        track = "unknown"
        scenario = "unknown"

        for anchor in ("datasets", "training-data", "tracks"):
            if anchor in segments:
                idx = segments.index(anchor)
                if idx + 1 < len(segments):
                    track = segments[idx + 1]
                if idx + 2 < len(segments):
                    scenario = segments[idx + 2]
                return track, scenario

        if len(segments) >= 2:
            track = segments[0]
            scenario = segments[1]
        elif len(segments) == 1:
            track = segments[0]
        return track, scenario

    def _ensure_schema(self) -> None:
        self._db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_catalog (
                r2_key TEXT PRIMARY KEY,
                size INTEGER NOT NULL DEFAULT 0,
                last_modified TEXT NOT NULL DEFAULT '',
                track TEXT NOT NULL DEFAULT 'unknown',
                scenario TEXT NOT NULL DEFAULT 'unknown',
                status TEXT NOT NULL DEFAULT 'pending',
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            );
            """
        )
        self._db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_catalog_meta (
                meta_key TEXT PRIMARY KEY,
                meta_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_vault_catalog_track ON vault_catalog(track);")
        self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_vault_catalog_scenario ON vault_catalog(scenario);")
        self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_vault_catalog_status ON vault_catalog(status);")
        self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_vault_catalog_deleted ON vault_catalog(is_deleted);")
        self._db_conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "r2_key": str(row["r2_key"]),
            "size": int(row["size"]),
            "last_modified": str(row["last_modified"]),
            "track": str(row["track"]),
            "scenario": str(row["scenario"]),
            "status": str(row["status"]),
            "is_deleted": bool(row["is_deleted"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "deleted_at": str(row["deleted_at"]) if row["deleted_at"] else None,
        }

    def _set_last_sync(self, timestamp: str) -> None:
        self._db_conn.execute(
            """
            INSERT INTO vault_catalog_meta(meta_key, meta_value, updated_at)
            VALUES ('last_sync', ?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET
                meta_value=excluded.meta_value,
                updated_at=excluded.updated_at;
            """,
            (timestamp, timestamp),
        )

    def _get_last_sync(self) -> str | None:
        cursor = self._db_conn.execute(
            "SELECT meta_value FROM vault_catalog_meta WHERE meta_key='last_sync' LIMIT 1;"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return str(row["meta_value"])

    def sync(self) -> dict[str, int]:
        remote_files = self.r2_client.list_files("")
        remote_map: dict[str, dict[str, Any]] = {}
        for entry in remote_files:
            key = str(entry.get("key", "")).strip().lstrip("/")
            if not key:
                continue
            remote_map[key] = {
                "size": int(entry.get("size", 0)),
                "last_modified": str(entry.get("last_modified", "")),
            }

        cursor = self._db_conn.execute("SELECT * FROM vault_catalog;")
        existing_rows = cursor.fetchall()
        existing_map = {str(row["r2_key"]): row for row in existing_rows}

        added = 0
        removed = 0
        unchanged = 0
        now = self._utc_now()

        for r2_key, metadata in remote_map.items():
            row = existing_map.get(r2_key)
            track, scenario = self._extract_track_scenario(r2_key)
            size = metadata["size"]
            last_modified = metadata["last_modified"]

            if row is None:
                self._db_conn.execute(
                    """
                    INSERT INTO vault_catalog(
                        r2_key, size, last_modified, track, scenario, status,
                        is_deleted, created_at, updated_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, NULL);
                    """,
                    (r2_key, size, last_modified, track, scenario, now, now),
                )
                added += 1
                continue

            old_size = int(row["size"])
            old_last_modified = str(row["last_modified"])
            was_deleted = bool(row["is_deleted"])
            changed_payload = old_size != size or old_last_modified != last_modified
            next_status = "pending" if changed_payload or was_deleted else str(row["status"])

            self._db_conn.execute(
                """
                UPDATE vault_catalog
                SET size=?, last_modified=?, track=?, scenario=?, status=?,
                    is_deleted=0, deleted_at=NULL, updated_at=?
                WHERE r2_key=?;
                """,
                (size, last_modified, track, scenario, next_status, now, r2_key),
            )
            unchanged += 1

        for row in existing_rows:
            r2_key = str(row["r2_key"])
            if r2_key in remote_map:
                continue
            if bool(row["is_deleted"]):
                continue
            self._db_conn.execute(
                """
                UPDATE vault_catalog
                SET is_deleted=1, status='deleted', deleted_at=?, updated_at=?
                WHERE r2_key=?;
                """,
                (now, now, r2_key),
            )
            removed += 1

        self._set_last_sync(now)
        self._db_conn.commit()
        return {"added": added, "removed": removed, "unchanged": unchanged}

    def find_by_track(self, track: str) -> list[dict[str, Any]]:
        normalized_track = self._required_value("track", track)
        cursor = self._db_conn.execute(
            """
            SELECT * FROM vault_catalog
            WHERE track=? AND is_deleted=0
            ORDER BY r2_key ASC;
            """,
            (normalized_track,),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def find_by_scenario(self, track: str, scenario: str) -> list[dict[str, Any]]:
        normalized_track = self._required_value("track", track)
        normalized_scenario = self._required_value("scenario", scenario)
        cursor = self._db_conn.execute(
            """
            SELECT * FROM vault_catalog
            WHERE track=? AND scenario=? AND is_deleted=0
            ORDER BY r2_key ASC;
            """,
            (normalized_track, normalized_scenario),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def find_unprocessed(self) -> list[dict[str, Any]]:
        cursor = self._db_conn.execute(
            """
            SELECT * FROM vault_catalog
            WHERE status='pending' AND is_deleted=0
            ORDER BY created_at ASC;
            """
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def mark_processing(self, r2_key: str) -> None:
        key = self._required_value("r2_key", r2_key).lstrip("/")
        now = self._utc_now()
        self._db_conn.execute(
            """
            UPDATE vault_catalog
            SET status='processing', updated_at=?
            WHERE r2_key=? AND is_deleted=0;
            """,
            (now, key),
        )
        self._db_conn.commit()

    def mark_complete(self, r2_key: str) -> None:
        key = self._required_value("r2_key", r2_key).lstrip("/")
        now = self._utc_now()
        self._db_conn.execute(
            """
            UPDATE vault_catalog
            SET status='complete', updated_at=?
            WHERE r2_key=? AND is_deleted=0;
            """,
            (now, key),
        )
        self._db_conn.commit()

    def get_stats(self) -> dict[str, Any]:
        total_cursor = self._db_conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS total_size FROM vault_catalog WHERE is_deleted=0;"
        )
        total_row = total_cursor.fetchone()
        total_files = int(total_row["count"]) if total_row else 0
        total_size = int(total_row["total_size"]) if total_row else 0

        by_track_cursor = self._db_conn.execute(
            """
            SELECT track, COUNT(*) AS count
            FROM vault_catalog
            WHERE is_deleted=0
            GROUP BY track
            ORDER BY track ASC;
            """
        )
        by_track = {str(row["track"]): int(row["count"]) for row in by_track_cursor.fetchall()}

        by_status_cursor = self._db_conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM vault_catalog
            WHERE is_deleted=0
            GROUP BY status
            ORDER BY status ASC;
            """
        )
        by_status = {str(row["status"]): int(row["count"]) for row in by_status_cursor.fetchall()}

        return {
            "total_files": total_files,
            "total_size_gb": round(total_size / (1024**3), 3),
            "by_track": by_track,
            "by_status": by_status,
            "last_sync": self._get_last_sync(),
        }

    def close(self) -> None:
        if self._owns_connection:
            self._db_conn.close()
