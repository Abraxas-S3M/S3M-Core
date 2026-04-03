"""Operating mode degradation controls for tactical edge runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OperatingMode(Enum):
    """Runtime operating modes reflecting battlefield resource posture."""

    MODE_A_FULL_EDGE = "mode_a_full_edge"
    MODE_B_CPU_CONSTRAINED = "mode_b_cpu_constrained"
    MODE_C_NETWORK_AUGMENTED = "mode_c_network_augmented"
    MODE_D_OFFLINE_SURVIVAL = "mode_d_offline_survival"


@dataclass(frozen=True)
class ModePolicy:
    """Execution permissions and limits derived from current mode."""

    mode: OperatingMode
    allow_gpu: bool
    allow_external_inference: bool


class DegradationController:
    """Tracks and returns active mode policy for model planner decisions."""

    def __init__(self, initial_mode: OperatingMode = OperatingMode.MODE_A_FULL_EDGE) -> None:
        self._mode = initial_mode

    def set_mode(self, mode: OperatingMode) -> None:
        self._mode = mode

    def current_policy(self) -> ModePolicy:
        return self.policy_for_mode(self._mode)

    @staticmethod
    def policy_for_mode(mode: OperatingMode) -> ModePolicy:
        if mode == OperatingMode.MODE_A_FULL_EDGE:
            return ModePolicy(mode=mode, allow_gpu=True, allow_external_inference=True)
        if mode == OperatingMode.MODE_B_CPU_CONSTRAINED:
            return ModePolicy(mode=mode, allow_gpu=False, allow_external_inference=True)
        if mode == OperatingMode.MODE_C_NETWORK_AUGMENTED:
            return ModePolicy(mode=mode, allow_gpu=True, allow_external_inference=True)
        if mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL:
            return ModePolicy(mode=mode, allow_gpu=False, allow_external_inference=False)
        # Defensive fallback for unexpected enum extension paths.
        return ModePolicy(mode=mode, allow_gpu=False, allow_external_inference=False)

