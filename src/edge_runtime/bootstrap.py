"""
Bootstrap orchestrator for austere edge runtime subsystems.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.edge_runtime.bearer_broker import BearerBroker, MessageClass
from src.edge_runtime.degradation_controller import DegradationController
from src.edge_runtime.durable_queue import DurableQueue, SyncReconciler
from src.edge_runtime.hardware_profiler import HardwareProfiler
from src.edge_runtime.health_surface import OperatorHealthSurface
from src.edge_runtime.model_planner import ModelExecutionPlanner


LOGGER = logging.getLogger(__name__)


class AustereEdgeRuntime:
    """Wires hardware profiling, mode control, routing, queueing, and health surfaces."""

    def __init__(self, queue_db_path: str = "data/edge_runtime/outbound_queue.db") -> None:
        self.profiler = HardwareProfiler()
        self.profile = self.profiler.run()
        self.broker = BearerBroker(on_link_change=self._on_link_change)
        self.controller = DegradationController(self.profile)
        self.planner = ModelExecutionPlanner(self.profile, self.controller)
        self.queue = DurableQueue(queue_db_path)
        self.reconciler = SyncReconciler(self.queue)
        self.health = OperatorHealthSurface(self.profiler, self.controller, self.broker, self.queue)

        LOGGER.info(
            "AustereEdgeRuntime booted tier=%s mode=%s",
            self.profile.tier.value,
            self.controller.current_mode.value,
        )

    def _on_link_change(self, any_up: bool) -> None:
        self.controller.report_link_state(any_up)
        if any_up:
            self.reconciler.run_sync()

    def status(self) -> Dict[str, Any]:
        return self.health.full_status()

    def plan_model(self, model_id: str, requested_tokens: int = 512) -> Dict[str, Any]:
        return self.planner.plan(model_id, requested_tokens).to_dict()

    def route_message(self, message_class_str: str, payload_size_kb: float = 0) -> Dict[str, Any]:
        message_class = MessageClass(message_class_str)
        return self.broker.route(message_class, payload_size_kb).to_dict()

    def enqueue_message(self, message_class: str, payload: object, priority: int = 5) -> str:
        return self.queue.enqueue(message_class=message_class, payload=payload, priority=priority)
