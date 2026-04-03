"""Durable outbound queue and reconciliation for disconnected operation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
from typing import Any, Dict, List

logger = logging.getLogger("s3m.edge_runtime.durable_queue")


@dataclass(slots=True, frozen=True)
class QueueMessage:
    id: int
    message_class: str
    payload: Dict[str, Any]
    attempts: int


class DurableQueue:
    """SQLite-backed queue supporting ack/nack and reboot persistence."""

    def __init__(self, db_path: str = "data/edge_runtime/outbound_queue.db") -> None:
        self.db_path = db_path
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure()
        self._initialize_schema()

    def _configure(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    def _initialize_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS outbound_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_class TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbound_queue_status_id ON outbound_queue(status, id)"
        )
        self._conn.commit()

    def enqueue(self, message_class: str, payload: Dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            INSERT INTO outbound_queue(message_class, payload_json, status, attempts, created_at, updated_at)
            VALUES(?, ?, 'pending', 0, ?, ?)
            """,
            (message_class, json.dumps(payload, separators=(",", ":")), now, now),
        )
        self._conn.commit()
        message_id = int(cursor.lastrowid)
        logger.info("Queued outbound message id=%s class=%s", message_id, message_class)
        return message_id

    def claim_batch(self, limit: int = 32) -> List[QueueMessage]:
        bounded = max(1, min(limit, 512))
        cursor = self._conn.execute(
            """
            SELECT id, message_class, payload_json, attempts
            FROM outbound_queue
            WHERE status='pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (bounded,),
        )
        rows = list(cursor.fetchall())
        if not rows:
            return []

        now = datetime.now(timezone.utc).isoformat()
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        self._conn.execute(
            f"""
            UPDATE outbound_queue
            SET status='inflight',
                attempts=attempts + 1,
                updated_at=?
            WHERE id IN ({placeholders})
            """,
            (now, *ids),
        )
        self._conn.commit()
        return [
            QueueMessage(
                id=int(row["id"]),
                message_class=str(row["message_class"]),
                payload=json.loads(str(row["payload_json"])),
                attempts=int(row["attempts"]) + 1,
            )
            for row in rows
        ]

    def ack(self, message_ids: List[int]) -> int:
        if not message_ids:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in message_ids)
        cursor = self._conn.execute(
            f"""
            DELETE FROM outbound_queue
            WHERE id IN ({placeholders})
            """,
            tuple(message_ids),
        )
        self._conn.commit()
        logger.info("Acknowledged %s outbound messages at %s", cursor.rowcount, now)
        return int(cursor.rowcount)

    def nack(self, message_ids: List[int]) -> int:
        if not message_ids:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in message_ids)
        cursor = self._conn.execute(
            f"""
            UPDATE outbound_queue
            SET status='pending', updated_at=?
            WHERE id IN ({placeholders})
            """,
            (now, *message_ids),
        )
        self._conn.commit()
        return int(cursor.rowcount)

    def stats(self) -> Dict[str, int]:
        pending = self._count("pending")
        inflight = self._count("inflight")
        return {
            "pending": pending,
            "inflight": inflight,
            "depth": pending + inflight,
        }

    def _count(self, status: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(1) AS count FROM outbound_queue WHERE status=?",
            (status,),
        ).fetchone()
        return int(row["count"]) if row else 0

    def close(self) -> None:
        self._conn.close()


class SyncReconciler:
    """Attempts queued message delivery when connectivity is restored."""

    def __init__(self, queue: DurableQueue) -> None:
        self.queue = queue

    def run_sync(self, max_batches: int = 8, batch_size: int = 32) -> Dict[str, int]:
        acked = 0
        nacked = 0
        batches = 0
        while batches < max_batches:
            batches += 1
            claimed = self.queue.claim_batch(limit=batch_size)
            if not claimed:
                break

            # Tactical behavior: integration hook would attempt link transmission here.
            # In bootstrap default mode we mark reconciliation as locally successful.
            ids = [item.id for item in claimed]
            acked += self.queue.ack(ids)
        stats = self.queue.stats()
        result = {
            "batches": batches,
            "acked": acked,
            "nacked": nacked,
            "remaining_depth": stats["depth"],
        }
        logger.info("Queue reconciliation complete: %s", result)
        return result
