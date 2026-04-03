"""
Unified operator health surface for austere runtime status.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from src.edge_runtime.bearer_broker import BearerBroker
from src.edge_runtime.degradation_controller import DegradationController
from src.edge_runtime.durable_queue import DurableQueue
from src.edge_runtime.hardware_profiler import HardwareProfiler


class OperatorHealthSurface:
    """Presents mission-relevant node status in a compact operator-facing view."""

    def __init__(
        self,
        profiler: HardwareProfiler,
        controller: DegradationController,
        broker: BearerBroker,
        queue: DurableQueue,
    ) -> None:
        self.profiler = profiler
        self.controller = controller
        self.broker = broker
        self.queue = queue

    def full_status(self) -> Dict[str, Any]:
        profile = self.profiler.profile or self.controller.profile
        policy = self.controller.current_policy()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node": {
                "tier": profile.tier.value,
                "cpu_cores": profile.cpu_cores,
                "ram_available_gb": profile.ram_available_gb,
                "gpu_detected": profile.gpu_detected,
                "thermal_c": profile.thermal_zone_c,
            },
            "operating_mode": {
                "mode": self.controller.current_mode.value,
                "description": policy.description,
                "max_concurrent_models": policy.max_concurrent_models,
                "gpu_allowed": policy.allow_gpu,
                "large_transfers_allowed": policy.allow_large_transfers,
                "summarization_interval_sec": policy.summarization_interval_sec,
            },
            "communications": {
                "any_bearer_up": self.broker.any_bearer_up(),
                "bearers": self.broker.bearer_status(),
            },
            "queue": self.queue.stats(),
            "transitions": self.controller.get_transition_log()[-10:],
        }

    def summary_line(self) -> str:
        mode = self.controller.current_mode.value
        bearers = len(self.broker.bearer_status())
        queued = self.queue.pending_count()
        return f"[{mode}] bearers={bearers} queued={queued}"
