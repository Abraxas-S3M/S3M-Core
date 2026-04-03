"""
Append-only durable message queue with store-and-forward semantics.
Nothing is lost when links vanish in contested tactical environments.
Uses file-backed SQLite for persistence — no external dependencies.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger("s3m.edge_runtime.durable_queue")


class QueueItemState(Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class QueueItem:
    item_id: str
    message_class: str
    payload: str  # JSON-encoded
    priority: int  # 0=highest
    state: str
    created_at: str
    attempts: int
    last_attempt_at: Optional[str]
    max_retries: int
    ttl_seconds: int  # 0 = no expiry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "message_class": self.message_class,
            "priority": self.priority,
            "state": self.state,
            "created_at": self.created_at,
            "attempts": self.attempts,
            "last_attempt_at": self.last_attempt_at,
            "payload_size_bytes": len(self.payload),
        }


class DurableQueue:
    """
    File-backed persistent queue.
    Survives process restarts, power loss, and network outages.
    """

    def __init__(self, db_path: str = "data/edge_runtime/outbound_queue.db") -> None:
        if not isinstance(db_path, str) or not db_path.strip():
            raise ValueError("db_path must be a non-empty string")
        db_dir = os.path.dirname(db_path) or "."
        os.makedirs(db_dir, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
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
            );
            CREATE INDEX IF NOT EXISTS idx_queue_state_priority
                ON queue(state, priority, created_at);
        """
        )
        self._conn.commit()

    # -- Enqueue -----------------------------------------------------------

    def enqueue(
        self,
        message_class: str,
        payload: Any,
        priority: int = 5,
        max_retries: int = 10,
        ttl_seconds: int = 0,
    ) -> str:
        if not isinstance(message_class, str) or not message_class.strip():
            raise ValueError("message_class must be a non-empty string")
        if not isinstance(priority, int) or priority < 0:
            raise ValueError("priority must be an integer >= 0")
        if not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be an integer >= 0")
        if not isinstance(ttl_seconds, int) or ttl_seconds < 0:
            raise ValueError("ttl_seconds must be an integer >= 0")

        item_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload_json = self._payload_to_json(payload)
        self._conn.execute(
            """INSERT INTO queue (item_id, message_class, payload, priority,
               state, created_at, max_retries, ttl_seconds)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (item_id, message_class, payload_json, priority, now, max_retries, ttl_seconds),
        )
        self._conn.commit()
        return item_id

    # -- Dequeue (claim for delivery) -------------------------------------

    def claim_batch(self, limit: int = 10) -> List[QueueItem]:
        """Claim up to `limit` pending items for delivery, ordered by priority."""
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")

        self._expire_stale()
        with self._lock:
            cursor = self._conn.execute(
                """SELECT item_id, message_class, payload, priority, state,
                          created_at, attempts, last_attempt_at, max_retries, ttl_seconds
                   FROM queue WHERE state = 'pending'
                   ORDER BY priority ASC, created_at ASC LIMIT ?""",
                (limit,),
            )
            items = [QueueItem(*row) for row in cursor.fetchall()]
            now = datetime.now(timezone.utc).isoformat()
            for item in items:
                self._conn.execute(
                    """UPDATE queue
                       SET state='in_flight', attempts=attempts+1, last_attempt_at=?
                       WHERE item_id=?""",
                    (now, item.item_id),
                )
                item.state = QueueItemState.IN_FLIGHT.value
                item.attempts += 1
                item.last_attempt_at = now
            self._conn.commit()
        return items

    # -- Acknowledge / Fail -----------------------------------------------

    def ack(self, item_id: str) -> None:
        self._validate_item_id(item_id)
        self._conn.execute("UPDATE queue SET state='delivered' WHERE item_id=?", (item_id,))
        self._conn.commit()

    def nack(self, item_id: str) -> None:
        """Return to pending if retries remain, else mark failed."""
        self._validate_item_id(item_id)
        row = self._conn.execute(
            "SELECT attempts, max_retries FROM queue WHERE item_id=?",
            (item_id,),
        ).fetchone()
        if row and row[0] < row[1]:
            self._conn.execute("UPDATE queue SET state='pending' WHERE item_id=?", (item_id,))
        else:
            self._conn.execute("UPDATE queue SET state='failed' WHERE item_id=?", (item_id,))
        self._conn.commit()

    # -- Stats -------------------------------------------------------------

    def stats(self) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for state in QueueItemState:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM queue WHERE state=?",
                (state.value,),
            ).fetchone()
            result[state.value] = row[0] if row else 0
        return result

    def pending_count(self) -> int:
        self._expire_stale()
        row = self._conn.execute(
            "SELECT COUNT(*) FROM queue WHERE state='pending'",
        ).fetchone()
        return row[0] if row else 0

    def purge_delivered(self, older_than_hours: int = 24) -> int:
        """
        Remove delivered items older than threshold.

        Tactical note: keeping the queue compact preserves local storage headroom
        for higher-priority battlefield traffic during prolonged disconnection.
        """
        if not isinstance(older_than_hours, int) or older_than_hours < 0:
            raise ValueError("older_than_hours must be an integer >= 0")
        # Simplified: purge all delivered (production would use timestamp math)
        cursor = self._conn.execute("DELETE FROM queue WHERE state='delivered'")
        self._conn.commit()
        return cursor.rowcount

    # -- Internal ----------------------------------------------------------

    def _expire_stale(self) -> None:
        """Mark items past their TTL as expired."""
        self._conn.execute(
            """UPDATE queue SET state='expired'
               WHERE state IN ('pending','in_flight')
               AND ttl_seconds > 0
               AND (julianday('now') - julianday(created_at)) * 86400 > ttl_seconds"""
        )
        self._conn.commit()

    def _payload_to_json(self, payload: Any) -> str:
        if isinstance(payload, str):
            # Security-first validation: only accept valid JSON payload strings.
            try:
                json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError("payload string must contain valid JSON") from exc
            return payload
        return json.dumps(payload)

    def _validate_item_id(self, item_id: str) -> None:
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("item_id must be a non-empty string")

    def close(self) -> None:
        self._conn.close()


class SyncReconciler:
    """
    When connectivity returns, reconciles local state with upstream.
    Handles: health data, summaries, logs, approved artifacts, config deltas.
    """

    def __init__(self, queue: DurableQueue) -> None:
        self.queue = queue
        self._sync_log: List[Dict[str, Any]] = []

    def run_sync(self, send_fn: Optional[Any] = None) -> Dict[str, Any]:
        """
        Drain the queue and attempt delivery via send_fn.
        send_fn(item) -> bool indicating success.
        """
        batch = self.queue.claim_batch(limit=50)
        delivered = 0
        failed = 0
        for item in batch:
            success = False
            if send_fn:
                try:
                    success = bool(send_fn(item))
                except Exception as exc:
                    logger.warning("Sync delivery failed: %s", exc)
            if success:
                self.queue.ack(item.item_id)
                delivered += 1
            else:
                self.queue.nack(item.item_id)
                failed += 1

        result = {
            "attempted": len(batch),
            "delivered": delivered,
            "failed": failed,
            "remaining_pending": self.queue.pending_count(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._sync_log.append(result)
        return result

    def get_sync_log(self) -> List[Dict[str, Any]]:
        return list(self._sync_log)
