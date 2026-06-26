"""Append-only, in-memory audit log for the Quad-Engine Orchestration Layer.

Tactical context:
    Every packet that flows through the orchestration layer is auditable so a
    commander or oversight officer can later reconstruct *what was recommended,
    by which engine, and whether a live model or a placeholder produced it*. The
    log deliberately records that no autonomous action was taken and that human
    review was required, preserving the human-in-the-loop guarantee.

    The buffer is bounded and entirely in-memory: it performs no disk writes
    that could leak classified payloads, no network egress, and never records
    model paths or credentials.
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """Thread-safe, bounded ring buffer of orchestration audit entries."""

    def __init__(self, *, max_entries: int = 1000) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries: Deque[Dict[str, Any]] = deque(maxlen=self._max_entries)
        self._lock = threading.Lock()

    def record(self, action: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Append an audit entry and return it."""
        entry = {
            "id": uuid.uuid4().hex[:12],
            "timestamp": _now_iso(),
            "action": str(action),
            "details": dict(details or {}),
        }
        with self._lock:
            self._entries.append(entry)
        return entry

    def recent(self, limit: int = 50, action: Optional[str] = None) -> List[Dict[str, Any]]:
        bounded = max(1, int(limit))
        with self._lock:
            items = list(self._entries)
        if action:
            items = [e for e in items if e["action"] == action]
        return items[-bounded:]

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_GLOBAL_AUDIT: Optional[AuditLog] = None
_GLOBAL_AUDIT_LOCK = threading.Lock()


def get_audit_log() -> AuditLog:
    """Return the process-wide quad-engine audit log singleton."""
    global _GLOBAL_AUDIT
    if _GLOBAL_AUDIT is None:
        with _GLOBAL_AUDIT_LOCK:
            if _GLOBAL_AUDIT is None:
                _GLOBAL_AUDIT = AuditLog()
    return _GLOBAL_AUDIT
