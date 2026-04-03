"""
Unified observability facade for field operators.
Single call returns everything an operator needs to understand node state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from src.edge_runtime.hardware_profiler import HardwareProfiler, NodeProfile
    from src.edge_runtime.degradation_controller import DegradationController
    from src.edge_runtime.bearer_broker import BearerBroker
    from src.edge_runtime.durable_queue import DurableQueue
except ImportError:  # pragma: no cover - allows isolated module testing.
    HardwareProfiler = Any  # type: ignore[assignment]
    NodeProfile = Any  # type: ignore[assignment]
    DegradationController = Any  # type: ignore[assignment]
    BearerBroker = Any  # type: ignore[assignment]
    DurableQueue = Any  # type: ignore[assignment]


class OperatorHealthSurface:
    """
    Exposes:
    - what links are up
    - which mode the node is in
    - what is queued
    - what was dropped
    - which models are active
    - whether the node is in degraded or recovery mode
    """

    def __init__(
        self,
        profiler: HardwareProfiler,
        controller: DegradationController,
        broker: BearerBroker,
        queue: DurableQueue,
    ) -> None:
        self._validate_collaborator(profiler, "profiler")
        self._validate_collaborator(controller, "controller")
        self._validate_collaborator(broker, "broker")
        self._validate_collaborator(queue, "queue")

        self.profiler = profiler
        self.controller = controller
        self.broker = broker
        self.queue = queue

    @staticmethod
    def _validate_collaborator(value: Any, name: str) -> None:
        # Tactical health reporting must fail fast on missing components.
        if value is None:
            raise ValueError(f"{name} must not be None")

    @staticmethod
    def _enum_or_raw(value: Any, default: Any) -> Any:
        if value is None:
            return default
        return getattr(value, "value", value)

    @staticmethod
    def _profile_or_none(profiler: HardwareProfiler) -> Optional[NodeProfile]:
        return getattr(profiler, "profile", None)

    def full_status(self) -> Dict[str, Any]:
        profile = self._profile_or_none(self.profiler)
        policy = self.controller.current_policy()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node": {
                "tier": self._enum_or_raw(getattr(profile, "tier", None), "unknown"),
                "cpu_cores": getattr(profile, "cpu_cores", 0) if profile else 0,
                "ram_available_gb": round(getattr(profile, "ram_available_gb", 0), 2)
                if profile
                else 0,
                "gpu_detected": getattr(profile, "gpu_detected", False) if profile else False,
                "thermal_c": getattr(profile, "thermal_zone_c", None) if profile else None,
            },
            "operating_mode": {
                "mode": self._enum_or_raw(self.controller.current_mode, "unknown"),
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
        """One-line status for constrained displays."""
        mode = self._enum_or_raw(self.controller.current_mode, "unknown")
        bearers_up = sum(
            1 for b in self.broker.bearer_status() if b.get("state") in ("up", "degraded")
        )
        pending = self.queue.pending_count()
        return f"[{mode}] bearers={bearers_up} queued={pending}"
