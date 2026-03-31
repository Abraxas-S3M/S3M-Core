"""Mission executor for behavior trees in tactical autonomy.

Executes behavior trees at fixed tick rates, tracks mission status transitions,
and records auditable autonomy decisions for after-action review.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional

from src.autonomy.models import AutonomyDecision, MissionStatus

from .nodes import BTNode, BTStatus


class MissionExecutor:
    """Thread-safe behavior tree executor with tactical audit logging."""

    def __init__(self, tree: BTNode, tick_rate_hz: float = 10.0) -> None:
        if tree is None:
            raise ValueError("tree is required")
        if tick_rate_hz <= 0:
            raise ValueError("tick_rate_hz must be > 0")
        self.tree = tree
        self.tick_rate_hz = float(tick_rate_hz)
        self.tick_interval = 1.0 / self.tick_rate_hz

        self._lock = threading.Lock()
        self._running = False
        self._paused = False
        self._aborted = False
        self._ticks_executed = 0
        self._started_at: Optional[datetime] = None
        self._ended_at: Optional[datetime] = None
        self._last_status: Optional[BTStatus] = None
        self._current_node_path: List[str] = []
        self._tick_log: List[Dict[str, Any]] = []
        self._context: Dict[str, Any] = {}

    def start(self, context: Dict[str, Any]) -> None:
        """Initialize mission execution state with fresh context."""
        with self._lock:
            self._context = context
            self._context.setdefault("mission_status", MissionStatus.ACTIVE.value)
            self._context.setdefault("decision_log", [])
            self._context.setdefault("executor_tick_log", [])
            self.tree.reset()
            self._running = True
            self._paused = False
            self._aborted = False
            self._ticks_executed = 0
            self._started_at = datetime.now(timezone.utc)
            self._ended_at = None
            self._last_status = None
            self._current_node_path = []
            self._tick_log = []

    def _snapshot_context(self, depth: int = 2) -> Dict[str, Any]:
        """Create bounded context snapshot for tactical audit entries."""
        if depth <= 0:
            return {}
        snapshot: Dict[str, Any] = {}
        for key, value in self._context.items():
            if key in {"decision_log", "executor_tick_log"}:
                continue
            if isinstance(value, dict) and depth > 1:
                try:
                    snapshot[key] = deepcopy(value)
                except Exception:
                    snapshot[key] = str(value)
            elif isinstance(value, (list, tuple)) and depth > 1:
                try:
                    snapshot[key] = deepcopy(value[:10]) if isinstance(value, list) else deepcopy(value)
                except Exception:
                    snapshot[key] = str(value)
            elif isinstance(value, (str, int, float, bool)) or value is None:
                snapshot[key] = value
            else:
                snapshot[key] = str(value)
        return snapshot

    def tick(self) -> BTStatus:
        """Run one behavior-tree tick and record tactical audit details."""
        with self._lock:
            if not self._running:
                raise RuntimeError("mission executor is not running")
            if self._paused:
                return BTStatus.RUNNING
            if self._aborted:
                self._last_status = BTStatus.FAILURE
                return BTStatus.FAILURE

            status = self.tree.tick(self._context)
            self._ticks_executed += 1
            self._last_status = status
            self._current_node_path = self.tree.get_active_path()

            tick_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tick": self._ticks_executed,
                "active_node": self._current_node_path[-1] if self._current_node_path else self.tree.name,
                "status": status.value,
                "context_snapshot": self._snapshot_context(depth=int(self._context.get("snapshot_depth", 2))),
            }
            self._tick_log.append(tick_entry)
            self._context["executor_tick_log"].append(tick_entry)

            if status in {BTStatus.SUCCESS, BTStatus.FAILURE}:
                self._running = False
                self._ended_at = datetime.now(timezone.utc)
                self._context["mission_status"] = (
                    MissionStatus.COMPLETED.value if status == BTStatus.SUCCESS else MissionStatus.FAILED.value
                )

            return status

    def run(self, context: Dict[str, Any], max_ticks: int = 10000) -> MissionStatus:
        """Run synchronously until completion, failure, abort, or tick budget."""
        if max_ticks <= 0:
            raise ValueError("max_ticks must be > 0")
        self.start(context)
        for _ in range(max_ticks):
            if self._aborted:
                with self._lock:
                    self._running = False
                    self._ended_at = datetime.now(timezone.utc)
                return MissionStatus.ABORTED
            status = self.tick()
            if status == BTStatus.SUCCESS:
                return MissionStatus.COMPLETED
            if status == BTStatus.FAILURE:
                return MissionStatus.FAILED if not self._aborted else MissionStatus.ABORTED
            time.sleep(self.tick_interval)
        with self._lock:
            self._running = False
            self._ended_at = datetime.now(timezone.utc)
        return MissionStatus.PAUSED

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            if self._aborted:
                return
            self._paused = False

    def abort(self) -> None:
        with self._lock:
            self._aborted = True
            self._running = False
            self._ended_at = datetime.now(timezone.utc)

    def get_status(self) -> Dict[str, Any]:
        """Return executor state for C2 dashboards and operator monitoring."""
        with self._lock:
            elapsed = 0.0
            if self._started_at:
                end = self._ended_at or datetime.now(timezone.utc)
                elapsed = max(0.0, (end - self._started_at).total_seconds())
            return {
                "running": self._running,
                "paused": self._paused,
                "aborted": self._aborted,
                "ticks_executed": self._ticks_executed,
                "time_elapsed_seconds": elapsed,
                "last_status": self._last_status.value if self._last_status else None,
                "current_node": self._current_node_path[-1] if self._current_node_path else None,
            }

    def get_decision_log(self) -> List[AutonomyDecision]:
        """Return full autonomy decision trace accumulated in context."""
        with self._lock:
            decisions = self._context.get("decision_log", [])
            return [d for d in decisions if isinstance(d, AutonomyDecision)]

    def get_current_node_path(self) -> List[str]:
        """Return active node path useful for tactical debugging and XAI."""
        with self._lock:
            return list(self._current_node_path)
