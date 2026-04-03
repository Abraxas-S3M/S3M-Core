"""
Durable outbound queue for disconnected tactical comms.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import os
import sqlite3
from threading import Lock
from typing import Callable, Dict, List, Optional
from uuid import uuid4


class QueueItemState(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class QueueItem:
    item_id: str
    message_class: str
    payload: str
    priority: int
    state: str
    created_at: str
    attempts: int
    last_attempt_at: Optional[str]
    max_retries: int
    ttl_seconds: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "item_id": self.item_id,
            "message_class": self.message_class,
            "priority": self.priority,
            "state": self.state,
            "created_at": self.created_at,
            "attempts": self.attempts,
            "last_attempt_at": self.last_attempt_at,
            "max_retries": self.max_retries,
            "ttl_seconds": self.ttl_seconds,
            "payload_size_bytes": len(self.payload.encode("utf-8", errors="ignore")),
        }


class DurableQueue:
    """SQLite-backed queue that preserves outbound traffic across outages."""

    def __init__(self, db_path: str = "data/edge_runtime/outbound_queue.db") -> None:
        self.db_path = db_path
        self._lock = Lock()
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue (
                    item_id TEXT PRIMARY KEY,
                    message_class TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    priority INTEGER DEFAULT 5,
                    state TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    last_attempt_at TEXT,
                    max_retries INTEGER DEFAULT 10,
                    ttl_seconds INTEGER DEFAULT 0
                )
                """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_state_priority_created ON queue(state, priority, created_at)"
            )
            self.conn.commit()

    def enqueue(
        self,
        message_class: str,
        payload: object,
        priority: int = 5,
        max_retries: int = 10,
        ttl_seconds: int = 0,
    ) -> str:
        item_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        payload_text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO queue (
                    item_id, message_class, payload, priority, state,
                    created_at, attempts, last_attempt_at, max_retries, ttl_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    item_id,
                    str(message_class),
                    payload_text,
                    int(priority),
                    QueueItemState.PENDING.value,
                    created_at,
                    int(max_retries),
                    int(ttl_seconds),
                ),
            )
            self.conn.commit()
        return item_id

    def claim_batch(self, limit: int = 10) -> List[QueueItem]:
        self._expire_stale()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM queue
                WHERE state = ?
                ORDER BY priority ASC, created_at ASC
                LIMIT ?
                """,
                (QueueItemState.PENDING.value, int(limit)),
            ).fetchall()
            items: List[QueueItem] = []
            for row in rows:
                self.conn.execute(
                    """
                    UPDATE queue
                    SET state = ?, attempts = attempts + 1, last_attempt_at = ?
                    WHERE item_id = ?
                    """,
                    (QueueItemState.IN_FLIGHT.value, now, row["item_id"]),
                )
                items.append(
                    QueueItem(
                        item_id=str(row["item_id"]),
                        message_class=str(row["message_class"]),
                        payload=str(row["payload"]),
                        priority=int(row["priority"]),
                        state=QueueItemState.IN_FLIGHT.value,
                        created_at=str(row["created_at"]),
                        attempts=int(row["attempts"]) + 1,
                        last_attempt_at=now,
                        max_retries=int(row["max_retries"]),
                        ttl_seconds=int(row["ttl_seconds"]),
                    )
                )
            self.conn.commit()
            return items

    def ack(self, item_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE queue SET state = ? WHERE item_id = ?",
                (QueueItemState.DELIVERED.value, item_id),
            )
            self.conn.commit()

    def nack(self, item_id: str) -> None:
        with self._lock:
            row = self.conn.execute(
                "SELECT attempts, max_retries FROM queue WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if row is None:
                return
            attempts = int(row["attempts"])
            max_retries = int(row["max_retries"])
            next_state = QueueItemState.PENDING.value if attempts < max_retries else QueueItemState.FAILED.value
            self.conn.execute(
                "UPDATE queue SET state = ? WHERE item_id = ?",
                (next_state, item_id),
            )
            self.conn.commit()

    def stats(self) -> Dict[str, int]:
        baseline: Dict[str, int] = {
            QueueItemState.PENDING.value: 0,
            QueueItemState.IN_FLIGHT.value: 0,
            QueueItemState.DELIVERED.value: 0,
            QueueItemState.FAILED.value: 0,
            QueueItemState.EXPIRED.value: 0,
        }
        with self._lock:
            rows = self.conn.execute("SELECT state, COUNT(*) AS count FROM queue GROUP BY state").fetchall()
        for row in rows:
            baseline[str(row["state"])] = int(row["count"])
        return baseline

    def pending_count(self) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS count FROM queue WHERE state = ?",
                (QueueItemState.PENDING.value,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def purge_delivered(self, older_than_hours: int = 24) -> int:
        del older_than_hours
        with self._lock:
            cursor = self.conn.execute(
                "DELETE FROM queue WHERE state = ?",
                (QueueItemState.DELIVERED.value,),
            )
            self.conn.commit()
            return int(cursor.rowcount or 0)

    def _expire_stale(self) -> None:
        with self._lock:
            self.conn.execute(
                """
                UPDATE queue
                SET state = ?
                WHERE ttl_seconds > 0
                  AND state IN (?, ?)
                  AND ((julianday('now') - julianday(created_at)) * 86400.0) >= ttl_seconds
                """,
                (
                    QueueItemState.EXPIRED.value,
                    QueueItemState.PENDING.value,
                    QueueItemState.IN_FLIGHT.value,
                ),
            )
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()


class SyncReconciler:
    """Attempts queue flushes whenever link availability returns."""

    def __init__(self, queue: DurableQueue) -> None:
        self.queue = queue
        self._sync_log: List[Dict[str, object]] = []

    def run_sync(self, send_fn: Optional[Callable[[QueueItem], bool]] = None) -> Dict[str, object]:
        batch = self.queue.claim_batch(limit=50)
        attempted = len(batch)
        delivered = 0
        failed = 0
        for item in batch:
            success = bool(send_fn(item)) if send_fn is not None else False
            if success:
                self.queue.ack(item.item_id)
                delivered += 1
            else:
                self.queue.nack(item.item_id)
                failed += 1

        result: Dict[str, object] = {
            "attempted": attempted,
            "delivered": delivered,
            "failed": failed,
            "remaining_pending": self.queue.pending_count(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._sync_log.append(result)
        if len(self._sync_log) > 1000:
            self._sync_log = self._sync_log[-1000:]
        return result

    def get_sync_log(self) -> List[Dict[str, object]]:
        return list(self._sync_log)
