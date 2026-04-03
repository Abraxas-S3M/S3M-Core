"""Hardware profiling primitives for tactical edge mode decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class HardwareTier(Enum):
    """Coarse platform classes used by runtime degradation policy."""

    FULL_EDGE = "full_edge"
    CPU_AUSTERE = "cpu_austere"


@dataclass
class NodeProfile:
    """
    Runtime hardware/link snapshot used by degradation controller.

    Tactical context: this profile captures whether the node can sustain
    full autonomous processing under denied, degraded, intermittent, and
    limited-bandwidth conditions.
    """

    tier: HardwareTier = HardwareTier.FULL_EDGE
    gpu_detected: bool = True
    active_links: List[str] = field(default_factory=list)
    thermal_zone_c: Optional[float] = None
    ram_available_gb: float = 8.0
