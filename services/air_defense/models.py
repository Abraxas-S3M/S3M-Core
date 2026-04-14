"""Data models for layered air-defense zone management.

Military context:
These structures model tactical defense echelons and their engagement
envelopes so allocation logic can prioritize long-range interceptors first,
then cascade inward if required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import sqrt
from typing import List, Tuple
from uuid import uuid4


class DefenseEchelon(str, Enum):
    """Doctrinal echelon classes used for layered air-defense coverage."""

    CLOSE = "close"
    SHORT = "short"
    MEDIUM = "medium"
    EXTENDED = "extended"


@dataclass
class DefenseZone:
    """A single tactical defense volume around a defended point."""

    name_en: str
    name_ar: str
    echelon: DefenseEchelon
    center: Tuple[float, float, float]
    inner_radius_m: float
    outer_radius_m: float
    min_altitude_m: float
    max_altitude_m: float
    priority: int
    zone_id: str = field(default_factory=lambda: str(uuid4()))
    active: bool = True
    assigned_effector_ids: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name_en.strip():
            raise ValueError("name_en must be a non-empty string")
        if not self.name_ar.strip():
            raise ValueError("name_ar must be a non-empty string")
        if not isinstance(self.echelon, DefenseEchelon):
            raise ValueError("echelon must be a DefenseEchelon instance")
        if len(self.center) != 3:
            raise ValueError("center must be a 3D coordinate tuple")

        cx, cy, cz = self.center
        self.center = (float(cx), float(cy), float(cz))

        self.inner_radius_m = float(self.inner_radius_m)
        self.outer_radius_m = float(self.outer_radius_m)
        self.min_altitude_m = float(self.min_altitude_m)
        self.max_altitude_m = float(self.max_altitude_m)

        if self.inner_radius_m < 0 or self.outer_radius_m <= 0:
            raise ValueError("zone radii must be positive with inner radius >= 0")
        if self.inner_radius_m >= self.outer_radius_m:
            raise ValueError("inner_radius_m must be lower than outer_radius_m")
        if self.min_altitude_m < 0 or self.max_altitude_m < 0:
            raise ValueError("zone altitudes must be non-negative")
        if self.min_altitude_m > self.max_altitude_m:
            raise ValueError("min_altitude_m must be <= max_altitude_m")
        if self.priority < 1:
            raise ValueError("priority must be >= 1")

    def contains_point(self, position: Tuple[float, float, float]) -> bool:
        """Check whether a target falls inside the zone's engagement envelope."""
        if len(position) != 3:
            raise ValueError("position must be a 3D coordinate tuple")

        x, y, altitude = (float(position[0]), float(position[1]), float(position[2]))
        center_x, center_y, _ = self.center

        # Tactical doctrine uses horizontal range for echelon assignment.
        horizontal_range_m = sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
        radial_match = self.inner_radius_m <= horizontal_range_m <= self.outer_radius_m
        altitude_match = self.min_altitude_m <= altitude <= self.max_altitude_m
        return radial_match and altitude_match
