"""Operator-facing runtime observability surface for austere operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Dict

from src.edge_runtime.bearer_broker import BearerBroker
from src.edge_runtime.degradation_controller import DegradationController
from src.edge_runtime.durable_queue import DurableQueue
from src.edge_runtime.hardware_profiler import HardwareProfiler

logger = logging.getLogger("s3m.edge_runtime.health_surface")


@dataclass(slots=True)
class OperatorHealthSurface:
    """Builds a compact operator status payload for edge runtime controls."""

    profiler: HardwareProfiler
    controller: DegradationController
    broker: BearerBroker
    queue: DurableQueue

    def full_status(self) -> Dict[str, Any]:
        profile = self.controller.profile
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node_tier": profile.tier.value,
            "operating_mode": self.controller.current_mode.value,
            "policy": asdict(self.controller.policy()),
            "bearers": self.broker.link_snapshot(),
            "queue": self.queue.stats(),
            "recent_transitions": self.controller.recent_transitions(),
        }
        logger.debug(
            "Health surface generated tier=%s mode=%s depth=%s",
            payload["node_tier"],
            payload["operating_mode"],
            payload["queue"]["depth"],
        )
        return payload
