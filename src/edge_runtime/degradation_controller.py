"""
Mode degradation controller for denied-edge mission continuity.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import time
from typing import Callable, Dict, List

from src.edge_runtime.hardware_profiler import HardwareTier, NodeProfile


class OperatingMode(str, Enum):
    MODE_A_FULL_EDGE = "full_edge"
    MODE_B_CPU_CONSTRAINED = "cpu_constrained"
    MODE_C_INTERMITTENT_LINK = "intermittent_link"
    MODE_D_OFFLINE_SURVIVAL = "offline_survival"


@dataclass(frozen=True)
class ModePolicy:
    mode: OperatingMode
    max_concurrent_models: int
    allow_gpu: bool
    allow_continuous_summarization: bool
    allow_large_transfers: bool
    allow_external_inference: bool
    summarization_interval_sec: int
    max_frame_rate: int
    queue_outbound: bool
    description: str


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
        description="Full capability posture with stable links and compute headroom.",
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
        description="CPU-constrained posture preserving tactical responsiveness.",
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
        description="Intermittent-link posture prioritizing store-and-forward traffic.",
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
        description="Offline survival posture maximizing endurance and mission continuity.",
    ),
}


@dataclass
class ModeTransition:
    from_mode: OperatingMode
    to_mode: OperatingMode
    reason: str
    timestamp: str


class DegradationController:
    """State machine converting link/thermal/resource signals into runtime modes."""

    def __init__(self, profile: NodeProfile) -> None:
        self.profile = profile
        self.current_mode: OperatingMode = self._initial_mode(profile)
        self._transitions: List[ModeTransition] = []
        self._subscribers: List[Callable[[OperatingMode, ModePolicy], None]] = []
        self._link_healthy: bool = bool(profile.active_links)
        self._link_last_seen: float = time.time() if self._link_healthy else 0.0

    def current_policy(self) -> ModePolicy:
        return MODE_POLICIES[self.current_mode]

    def subscribe(self, callback: Callable[[OperatingMode, ModePolicy], None]) -> None:
        self._subscribers.append(callback)

    def report_link_state(self, any_bearer_up: bool) -> None:
        self._link_healthy = bool(any_bearer_up)
        if self._link_healthy:
            self._link_last_seen = time.time()
        self._reevaluate()

    def report_thermal(self, temp_c: float) -> None:
        self.profile.thermal_zone_c = float(temp_c)
        self._reevaluate()

    def force_mode(self, mode: OperatingMode, reason: str) -> None:
        self._transition(mode, reason)

    def get_transition_log(self) -> List[Dict[str, str]]:
        return [
            {
                "from_mode": t.from_mode.value,
                "to_mode": t.to_mode.value,
                "reason": t.reason,
                "timestamp": t.timestamp,
            }
            for t in self._transitions
        ]

    def _reevaluate(self) -> None:
        no_link_for = 0.0 if self._link_healthy else max(0.0, time.time() - self._link_last_seen)
        thermal = self.profile.thermal_zone_c

        if (not self.profile.gpu_detected and no_link_for > 300.0) or no_link_for > 600.0:
            self._transition(OperatingMode.MODE_D_OFFLINE_SURVIVAL, f"link_down_{int(no_link_for)}s")
            return

        if no_link_for > 60.0:
            self._transition(OperatingMode.MODE_C_INTERMITTENT_LINK, f"link_unstable_{int(no_link_for)}s")
            return

        if (not self.profile.gpu_detected) or (thermal is not None and thermal > 85.0) or (self.profile.ram_available_gb < 4.0):
            self._transition(OperatingMode.MODE_B_CPU_CONSTRAINED, "resource_constrained")
            return

        self._transition(OperatingMode.MODE_A_FULL_EDGE, "nominal")

    def _transition(self, new_mode: OperatingMode, reason: str) -> None:
        if new_mode == self.current_mode:
            return
        transition = ModeTransition(
            from_mode=self.current_mode,
            to_mode=new_mode,
            reason=str(reason),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.current_mode = new_mode
        self._transitions.append(transition)
        policy = MODE_POLICIES[new_mode]
        for callback in list(self._subscribers):
            try:
                callback(new_mode, policy)
            except Exception:
                continue

    @staticmethod
    def _initial_mode(profile: NodeProfile) -> OperatingMode:
        if profile.tier == HardwareTier.CPU_AUSTERE:
            return OperatingMode.MODE_B_CPU_CONSTRAINED
        if not profile.active_links:
            return OperatingMode.MODE_D_OFFLINE_SURVIVAL
        return OperatingMode.MODE_A_FULL_EDGE

    @staticmethod
    def service_tiers() -> Dict[str, Dict[str, object]]:
        return {
            "llm_inference_q4": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "threat_classifier": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "anomaly_detector": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "behavior_tree_exec": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "sensor_fusion_ekf": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "arabic_nlp_keyword": {"tier": 0, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "object_detector": {"tier": 1, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "llm_inference_fp16": {"tier": 1, "cpu_safe": True, "offline_safe": True, "low_bw_safe": True},
            "bulk_log_sync": {"tier": 1, "cpu_safe": True, "offline_safe": False, "low_bw_safe": True},
            "simulation_engine": {"tier": 2, "cpu_safe": False, "offline_safe": True, "low_bw_safe": False},
            "model_fine_tune": {"tier": 2, "cpu_safe": False, "offline_safe": True, "low_bw_safe": False},
        }
