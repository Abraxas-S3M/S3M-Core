"""
Explicit operating-mode state machine.
Evaluates hardware profile + link state and enforces mode transitions
across all S3M layers.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List

from src.edge_runtime.hardware_profiler import HardwareTier, NodeProfile

logger = logging.getLogger("s3m.edge_runtime.degradation")


class OperatingMode(Enum):
    """Degradation modes from the gap analysis, explicit and enforceable."""

    MODE_A_FULL_EDGE = "full_edge"
    MODE_B_CPU_CONSTRAINED = "cpu_constrained"
    MODE_C_INTERMITTENT_LINK = "intermittent_link"
    MODE_D_OFFLINE_SURVIVAL = "offline_survival"


@dataclass
class ModePolicy:
    """What each mode permits or restricts."""

    mode: OperatingMode
    max_concurrent_models: int
    allow_gpu: bool
    allow_continuous_summarization: bool
    allow_large_transfers: bool
    allow_external_inference: bool
    summarization_interval_sec: int  # 0 = continuous, >0 = periodic
    max_frame_rate: int  # sensor sample cap
    queue_outbound: bool  # force store-and-forward
    description: str = ""


MODE_POLICIES: Dict[OperatingMode, ModePolicy] = {
    OperatingMode.MODE_A_FULL_EDGE: ModePolicy(
        mode=OperatingMode.MODE_A_FULL_EDGE,
        max_concurrent_models=4,
        allow_gpu=True,
        allow_continuous_summarization=True,
        allow_large_transfers=True,
        allow_external_inference=True,
        summarization_interval_sec=0,
        max_frame_rate=30,
        queue_outbound=False,
        description="Full edge: all models, all bearers, GPU acceleration.",
    ),
    OperatingMode.MODE_B_CPU_CONSTRAINED: ModePolicy(
        mode=OperatingMode.MODE_B_CPU_CONSTRAINED,
        max_concurrent_models=2,
        allow_gpu=False,
        allow_continuous_summarization=False,
        allow_large_transfers=True,
        allow_external_inference=True,
        summarization_interval_sec=60,
        max_frame_rate=10,
        queue_outbound=False,
        description="CPU constrained: smaller models, periodic summarization.",
    ),
    OperatingMode.MODE_C_INTERMITTENT_LINK: ModePolicy(
        mode=OperatingMode.MODE_C_INTERMITTENT_LINK,
        max_concurrent_models=2,
        allow_gpu=True,
        allow_continuous_summarization=False,
        allow_large_transfers=False,
        allow_external_inference=False,
        summarization_interval_sec=120,
        max_frame_rate=15,
        queue_outbound=True,
        description="Intermittent link: local autonomy, queued outbound, no large transfers.",
    ),
    OperatingMode.MODE_D_OFFLINE_SURVIVAL: ModePolicy(
        mode=OperatingMode.MODE_D_OFFLINE_SURVIVAL,
        max_concurrent_models=1,
        allow_gpu=False,
        allow_continuous_summarization=False,
        allow_large_transfers=False,
        allow_external_inference=False,
        summarization_interval_sec=300,
        max_frame_rate=5,
        queue_outbound=True,
        description="Offline survival: local-only event processing, store-and-forward journal.",
    ),
}


@dataclass
class ModeTransition:
    """Recorded transition between operational modes."""

    from_mode: OperatingMode
    to_mode: OperatingMode
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DegradationController:
    """
    Continuously evaluates conditions and enforces the correct operating mode.
    Other S3M services query current_policy() before loading models,
    sending messages, or starting pipelines.
    """

    def __init__(self, profile: NodeProfile) -> None:
        self.profile = profile
        self.current_mode = self._initial_mode(profile)
        self.policy = MODE_POLICIES[self.current_mode]
        self.transition_log: List[ModeTransition] = []
        self._subscribers: List[Callable[[OperatingMode, ModePolicy], None]] = []
        self._link_healthy = bool(profile.active_links)
        self._link_last_seen: float = time.time()
        logger.info("Degradation controller init -> %s", self.current_mode.value)

    def current_policy(self) -> ModePolicy:
        return self.policy

    def subscribe(self, callback: Callable[[OperatingMode, ModePolicy], None]) -> None:
        """Register to be notified on mode transitions."""
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._subscribers.append(callback)

    def report_link_state(self, any_bearer_up: bool) -> None:
        """Called by bearer broker whenever link state changes."""
        if not isinstance(any_bearer_up, bool):
            raise TypeError("any_bearer_up must be a bool")
        now = time.time()
        if any_bearer_up:
            self._link_healthy = True
            self._link_last_seen = now
        else:
            self._link_healthy = False
        self._reevaluate()

    def report_thermal(self, temp_c: float) -> None:
        """Called by Jetson monitor or OS thermal watcher."""
        if not isinstance(temp_c, (int, float)):
            raise TypeError("temp_c must be numeric")
        thermal = float(temp_c)
        if not math.isfinite(thermal):
            raise ValueError("temp_c must be finite")
        self.profile = NodeProfile(**{**self.profile.__dict__, "thermal_zone_c": thermal})
        self._reevaluate()

    def force_mode(self, mode: OperatingMode, reason: str = "operator_override") -> None:
        if not isinstance(mode, OperatingMode):
            raise TypeError("mode must be an OperatingMode")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        self._transition(mode, reason)

    def get_transition_log(self) -> List[Dict[str, Any]]:
        return [
            {
                "from": transition.from_mode.value,
                "to": transition.to_mode.value,
                "reason": transition.reason,
                "timestamp": transition.timestamp,
            }
            for transition in self.transition_log
        ]

    def _reevaluate(self) -> None:
        """Core decision: which mode should we be in right now?"""
        profile = self.profile
        link_down_sec = time.time() - self._link_last_seen if not self._link_healthy else 0.0

        # Tactical context: prolonged link loss on CPU-only hardware requires
        # strict local-only survival operations to preserve mission continuity.
        if link_down_sec > 300 and not profile.gpu_detected:
            self._transition(OperatingMode.MODE_D_OFFLINE_SURVIVAL, "no_link_5min_cpu_only")
            return

        if link_down_sec > 600:
            self._transition(OperatingMode.MODE_D_OFFLINE_SURVIVAL, "no_link_10min")
            return

        if link_down_sec > 60:
            self._transition(OperatingMode.MODE_C_INTERMITTENT_LINK, "link_intermittent")
            return

        thermal_hot = (profile.thermal_zone_c or 0.0) > 85.0
        if not profile.gpu_detected or thermal_hot or profile.ram_available_gb < 4:
            self._transition(OperatingMode.MODE_B_CPU_CONSTRAINED, "hw_constrained")
            return

        self._transition(OperatingMode.MODE_A_FULL_EDGE, "all_resources_available")

    def _transition(self, new_mode: OperatingMode, reason: str) -> None:
        if new_mode == self.current_mode:
            return
        old_mode = self.current_mode
        self.current_mode = new_mode
        self.policy = MODE_POLICIES[new_mode]
        transition = ModeTransition(from_mode=old_mode, to_mode=new_mode, reason=reason)
        self.transition_log.append(transition)
        logger.warning("Mode transition: %s -> %s (%s)", old_mode.value, new_mode.value, reason)
        for callback in self._subscribers:
            try:
                callback(new_mode, self.policy)
            except Exception as exc:  # pragma: no cover
                logger.error("Subscriber callback failed: %s", exc)

    @staticmethod
    def _initial_mode(profile: NodeProfile) -> OperatingMode:
        if profile.tier == HardwareTier.CPU_AUSTERE:
            return OperatingMode.MODE_B_CPU_CONSTRAINED
        if not profile.active_links:
            return OperatingMode.MODE_D_OFFLINE_SURVIVAL
        return OperatingMode.MODE_A_FULL_EDGE

    @staticmethod
    def service_tiers() -> Dict[str, Dict[str, Any]]:
        """
        Tier 0: must run on CPU-only, offline.
        Tier 1: runs better with GPU but functional on CPU.
        Tier 2: GPU-only optional services.
        """
        return {
            "llm_inference_q4": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "threat_classifier": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "anomaly_detector": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "behavior_tree_exec": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "sensor_fusion_ekf": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "arabic_nlp_keyword": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "object_detector": {"tier": 1, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "llm_inference_fp16": {"tier": 1, "cpu_safe": False, "offline_safe": True, "low_bw_safe": True},
            "simulation_engine": {"tier": 2, "cpu_safe": False, "offline_safe": True, "low_bw_safe": True},
            "model_fine_tune": {"tier": 2, "cpu_safe": False, "offline_safe": True, "low_bw_safe": False},
            "bulk_log_sync": {"tier": 1, "cpu_safe": True, "offline_safe": False, "low_bw_safe": False},
        }
