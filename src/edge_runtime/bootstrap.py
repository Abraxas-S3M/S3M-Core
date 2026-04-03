"""Boot sequence and integration entrypoint for austere edge runtime."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any, Dict, Optional

from src.edge_runtime.bearer_broker import BearerBroker
from src.edge_runtime.degradation_controller import DegradationController
from src.edge_runtime.durable_queue import DurableQueue, SyncReconciler
from src.edge_runtime.health_surface import OperatorHealthSurface
from src.edge_runtime.hardware_profiler import HardwareProfiler
from src.edge_runtime.model_planner import ModelExecutionPlanner

logger = logging.getLogger("s3m.edge_runtime.bootstrap")

_runtime_lock = Lock()
_runtime_instance: Optional["AustereEdgeRuntime"] = None


class AustereEdgeRuntime:
    """Single object that owns all runtime subsystems."""

    def __init__(self, queue_db_path: str = "data/edge_runtime/outbound_queue.db") -> None:
        # Step 1: Profile hardware.
        self.profiler = HardwareProfiler()
        self.profile = self.profiler.run()
        logger.info("Node classified as: %s", self.profile.tier.value)

        # Step 2: Initialize bearer broker.
        self.broker = BearerBroker(on_link_change=self._on_link_change)

        # Step 3: Initialize degradation controller.
        self.controller = DegradationController(self.profile)

        # Step 4: Initialize model planner.
        self.planner = ModelExecutionPlanner(self.profile, self.controller)

        # Step 5: Initialize durable queue.
        self.queue = DurableQueue(db_path=queue_db_path)
        self.reconciler = SyncReconciler(self.queue)

        # Step 6: Health surface.
        self.health = OperatorHealthSurface(
            self.profiler,
            self.controller,
            self.broker,
            self.queue,
        )

        logger.info(
            "Austere Edge Runtime initialized: mode=%s",
            self.controller.current_mode.value,
        )

    def _on_link_change(self, any_up: bool) -> None:
        self.controller.report_link_state(any_up)
        if any_up:
            logger.info("Link recovered; triggering sync reconciliation.")
            self.reconciler.run_sync()

    def status(self) -> Dict[str, Any]:
        return self.health.full_status()

    def close(self) -> None:
        self.queue.close()


def initialize_edge_runtime(queue_db_path: str = "data/edge_runtime/outbound_queue.db") -> AustereEdgeRuntime:
    """Idempotently initialize the global runtime singleton."""
    global _runtime_instance
    with _runtime_lock:
        if _runtime_instance is None:
            _runtime_instance = AustereEdgeRuntime(queue_db_path=queue_db_path)
            logger.info("Global edge runtime instance created")
        return _runtime_instance


def get_edge_runtime() -> AustereEdgeRuntime:
    """Return runtime singleton, initializing with default paths if needed."""
    runtime = _runtime_instance
    if runtime is not None:
        return runtime
    return initialize_edge_runtime()


def get_edge_runtime_status() -> Dict[str, Any]:
    """Convenience status accessor for API routes."""
    return get_edge_runtime().status()

