"""Degradation controller for disconnected or constrained tactical operation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Deque, Dict, List

from src.edge_runtime.hardware_profiler import HardwareTier, NodeProfile

logger = logging.getLogger("s3m.edge_runtime.degradation_controller")


class OperatingMode(str, Enum):
    FULL_EDGE = "FULL_EDGE"
    CPU_CONSTRAINED = "CPU_CONSTRAINED"
    INTERMITTENT_LINK = "INTERMITTENT_LINK"
    OFFLINE_SURVIVAL = "OFFLINE_SURVIVAL"


@dataclass(slots=True, frozen=True)
class ModePolicy:
    max_concurrent_models: int
    allow_gpu: bool
    allow_large_transfers: bool
    summarization_interval: int
    max_frame_rate: int
    queue_outbound: bool


class DegradationController:
    """Policy state machine for austere S3M runtime modes."""

    def __init__(self, profile: NodeProfile) -> None:
        self.profile = profile
        self._link_up = True
        self.current_mode = self._initial_mode_for_tier(profile.tier)
        self._transitions: Deque[Dict[str, str]] = deque(maxlen=50)
        self._record_transition("bootstrap")
        logger.info("Degradation controller booted mode=%s", self.current_mode.value)

    def policy(self) -> ModePolicy:
        if self.current_mode == OperatingMode.FULL_EDGE:
            return ModePolicy(
                max_concurrent_models=4 if self.profile.gpu_available else 2,
                allow_gpu=self.profile.gpu_available,
                allow_large_transfers=True,
                summarization_interval=120,
                max_frame_rate=30,
                queue_outbound=False,
            )
        if self.current_mode == OperatingMode.CPU_CONSTRAINED:
            return ModePolicy(
                max_concurrent_models=1,
                allow_gpu=False,
                allow_large_transfers=False,
                summarization_interval=45,
                max_frame_rate=10,
                queue_outbound=True,
            )
        if self.current_mode == OperatingMode.INTERMITTENT_LINK:
            return ModePolicy(
                max_concurrent_models=2 if self.profile.gpu_available else 1,
                allow_gpu=self.profile.gpu_available,
                allow_large_transfers=False,
                summarization_interval=30,
                max_frame_rate=8,
                queue_outbound=True,
            )
        return ModePolicy(
            max_concurrent_models=1,
            allow_gpu=False,
            allow_large_transfers=False,
            summarization_interval=20,
            max_frame_rate=5,
            queue_outbound=True,
        )

    def service_tiers(self) -> Dict[str, int]:
        """Declare tactical service degradation priority for this mode."""
        critical = {
            "command_control": 0,
            "situational_awareness": 0,
            "navigation": 0,
            "health_monitoring": 0,
        }
        important = {
            "sensor_fusion": 1,
            "threat_detection": 1,
            "intel_briefing": 1,
            "comms_relay": 1,
        }
        deferrable = {
            "dashboard_rendering": 2,
            "bulk_sync": 2,
            "model_retraining": 2,
            "archive_export": 2,
        }
        tiers = {**critical, **important, **deferrable}

        if self.current_mode == OperatingMode.FULL_EDGE:
            return tiers
        if self.current_mode == OperatingMode.CPU_CONSTRAINED:
            tiers["sensor_fusion"] = 2
            tiers["intel_briefing"] = 2
            return tiers
        if self.current_mode == OperatingMode.INTERMITTENT_LINK:
            tiers["bulk_sync"] = 2
            tiers["comms_relay"] = 0
            return tiers
        # OFFLINE_SURVIVAL
        tiers["comms_relay"] = 2
        tiers["threat_detection"] = 0
        tiers["sensor_fusion"] = 0
        tiers["intel_briefing"] = 2
        return tiers

    def report_link_state(self, any_up: bool) -> None:
        self._link_up = any_up
        next_mode = self._derive_mode()
        if next_mode != self.current_mode:
            logger.warning(
                "Operating mode transition %s -> %s due to link_up=%s",
                self.current_mode.value,
                next_mode.value,
                any_up,
            )
            self.current_mode = next_mode
            self._record_transition("link_state")

    def recent_transitions(self) -> List[Dict[str, str]]:
        return list(self._transitions)

    def _derive_mode(self) -> OperatingMode:
        if not self._link_up:
            return OperatingMode.OFFLINE_SURVIVAL
        if self.profile.tier == HardwareTier.CPU_AUSTERE:
            return OperatingMode.CPU_CONSTRAINED
        if self.profile.tier in {HardwareTier.VEHICLE_NODE, HardwareTier.EDGE_GPU}:
            return OperatingMode.INTERMITTENT_LINK
        return OperatingMode.FULL_EDGE

    def _initial_mode_for_tier(self, tier: HardwareTier) -> OperatingMode:
        if tier == HardwareTier.CPU_AUSTERE:
            return OperatingMode.CPU_CONSTRAINED
        if tier in {HardwareTier.EDGE_GPU, HardwareTier.VEHICLE_NODE}:
            return OperatingMode.INTERMITTENT_LINK
        return OperatingMode.FULL_EDGE

    def _record_transition(self, reason: str) -> None:
        self._transitions.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": self.current_mode.value,
                "reason": reason,
            }
        )
