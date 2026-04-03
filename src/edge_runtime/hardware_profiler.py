"""Hardware profiling primitives for edge planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HardwareTier(Enum):
    """Hardware capability tiers used by runtime planners."""

    TIER_0_AUSTERE = "tier_0_austere"
    TIER_1_BALANCED = "tier_1_balanced"
    TIER_2_ACCELERATED = "tier_2_accelerated"


@dataclass(frozen=True)
class NodeProfile:
    """Describes local node capability for tactical model execution."""

    tier: HardwareTier
    ram_available_gb: float
    gpu_detected: bool
