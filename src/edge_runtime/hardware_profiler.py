"""Hardware profiling primitives for tactical edge mode decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
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

    def __post_init__(self) -> None:
        if not isinstance(self.tier, HardwareTier):
            raise TypeError("tier must be a HardwareTier")
        if not isinstance(self.gpu_detected, bool):
            raise TypeError("gpu_detected must be a bool")
        if not isinstance(self.active_links, list) or any(
            not isinstance(link, str) for link in self.active_links
        ):
            raise TypeError("active_links must be a list[str]")
        if not isinstance(self.ram_available_gb, (int, float)):
            raise TypeError("ram_available_gb must be numeric")
        ram = float(self.ram_available_gb)
        if not math.isfinite(ram) or ram < 0:
            raise ValueError("ram_available_gb must be finite and non-negative")
        self.ram_available_gb = ram
        if self.thermal_zone_c is not None:
            if not isinstance(self.thermal_zone_c, (int, float)):
                raise TypeError("thermal_zone_c must be numeric when provided")
            thermal = float(self.thermal_zone_c)
            if not math.isfinite(thermal):
                raise ValueError("thermal_zone_c must be finite")
            self.thermal_zone_c = thermal
