"""Force composition builder for tactical scenario generation."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Tuple
import random

from src.simulation.models import EntityType, ForceComposition


class ForceBuilder:
    """Build reusable military force templates for simulation scenarios."""

    def __init__(self, bounds: Tuple[Tuple[float, float, float], Tuple[float, float, float]] = ((0, 0, 0), (1000, 1000, 200))) -> None:
        self.bounds = bounds
        self._rng = random.Random(7)

    def _random_position(self, min_alt: float = 0.0, max_alt: float = 120.0) -> tuple[float, float, float]:
        (min_x, min_y, _), (max_x, max_y, max_z) = self.bounds
        z_hi = min(max_alt, max_z)
        return (
            self._rng.uniform(min_x, max_x),
            self._rng.uniform(min_y, max_y),
            self._rng.uniform(min_alt, z_hi),
        )

    def _normalize_units(self, units: List[dict]) -> List[dict]:
        normalized = []
        for unit in units:
            if not isinstance(unit, dict):
                raise ValueError("each unit must be a dictionary")
            raw_type = unit.get("type", EntityType.UNKNOWN)
            if not isinstance(raw_type, EntityType):
                raw_type = EntityType(str(raw_type))
            count = int(unit.get("count", 0))
            if count <= 0:
                raise ValueError("unit count must be > 0")
            pos = unit.get("starting_position", unit.get("position", self._random_position()))
            if isinstance(pos, list):
                pos = tuple(pos)
            if not isinstance(pos, tuple) or len(pos) != 3:
                raise ValueError("starting_position/position must be length-3 tuple/list")
            behavior = str(unit.get("behavior", "hold")).strip() or "hold"
            normalized.append(
                {
                    "type": raw_type,
                    "count": count,
                    "starting_position": (float(pos[0]), float(pos[1]), float(pos[2])),
                    "behavior": behavior,
                }
            )
        return normalized

    def create_force(self, name: str, allegiance: str, units: List[dict]) -> ForceComposition:
        """Create validated force composition from custom unit definitions."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if allegiance not in {"friendly", "enemy"}:
            raise ValueError("allegiance must be 'friendly' or 'enemy'")
        return ForceComposition(force_name=name, allegiance=allegiance, units=self._normalize_units(units))

    def create_standard_patrol_force(self) -> ForceComposition:
        """Create a 4-UAV diamond patrol package for urban reconnaissance."""
        center = self._random_position(min_alt=60, max_alt=120)
        return self.create_force(
            name="Blue Force Patrol",
            allegiance="friendly",
            units=[
                {
                    "type": EntityType.FRIENDLY_UAV,
                    "count": 4,
                    "starting_position": center,
                    "behavior": "patrol",
                }
            ],
        )

    def create_standard_opfor(self) -> ForceComposition:
        """Create baseline adversary package: UAV scouts and infantry ambush."""
        return self.create_force(
            name="Red Force OpFor",
            allegiance="enemy",
            units=[
                {
                    "type": EntityType.ENEMY_UAV,
                    "count": 3,
                    "starting_position": self._random_position(min_alt=70, max_alt=140),
                    "behavior": "intercept",
                },
                {
                    "type": EntityType.ENEMY_INFANTRY,
                    "count": 5,
                    "starting_position": self._random_position(min_alt=0, max_alt=5),
                    "behavior": "ambush",
                },
            ],
        )

    def create_air_defense_force(self) -> ForceComposition:
        """Create enemy SAM/interceptor force for contested-airspace training."""
        return self.create_force(
            name="Red Air Defense",
            allegiance="enemy",
            units=[
                {
                    "type": EntityType.ENEMY_UGV,
                    "count": 2,
                    "starting_position": self._random_position(min_alt=0, max_alt=3),
                    "behavior": "sam_site",
                },
                {
                    "type": EntityType.ENEMY_UAV,
                    "count": 4,
                    "starting_position": self._random_position(min_alt=90, max_alt=160),
                    "behavior": "intercept",
                },
            ],
        )

    def create_convoy(self) -> ForceComposition:
        """Create friendly convoy with UAV escorts for route-security drills."""
        return self.create_force(
            name="Blue Convoy",
            allegiance="friendly",
            units=[
                {
                    "type": EntityType.FRIENDLY_UGV,
                    "count": 6,
                    "starting_position": self._random_position(min_alt=0, max_alt=1),
                    "behavior": "convoy",
                },
                {
                    "type": EntityType.FRIENDLY_UAV,
                    "count": 2,
                    "starting_position": self._random_position(min_alt=80, max_alt=120),
                    "behavior": "escort",
                },
            ],
        )

    def scale_force(self, force: ForceComposition, multiplier: float) -> ForceComposition:
        """Scale force size for stress-testing tactical coordination performance."""
        if not isinstance(force, ForceComposition):
            raise ValueError("force must be ForceComposition")
        if not isinstance(multiplier, (int, float)) or float(multiplier) <= 0:
            raise ValueError("multiplier must be positive")
        scaled_units = []
        for unit in force.units:
            scaled_count = max(1, int(unit["count"] * float(multiplier)))
            scaled_units.append(
                {
                    "type": unit["type"],
                    "count": scaled_count,
                    "starting_position": unit["starting_position"],
                    "behavior": unit["behavior"],
                }
            )
        return replace(force, units=scaled_units)
