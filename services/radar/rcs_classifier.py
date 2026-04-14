"""RCS-based target classification for tactical radar plots.

Military context:
These rules provide a deterministic first-pass class estimate so batteries can
prioritize low-RCS threats (UAVs/cruise missiles) before full multi-sensor ID.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from services.radar.models import RCSClassification


@dataclass(frozen=True)
class RCSClassifier:
    """Classify airborne contacts using radar cross section and kinematics."""

    ballistic_speed_threshold_mps: float = 500.0
    fighter_speed_threshold_mps: float = 180.0
    helicopter_speed_threshold_mps: float = 110.0

    def classify(self, rcs_m2: float, radial_velocity_mps: float = 0.0) -> RCSClassification:
        rcs = float(rcs_m2)
        speed = abs(float(radial_velocity_mps))
        if rcs < 0.0:
            raise ValueError("rcs_m2 must be non-negative")

        # Tactical priority: high-speed low-RCS returns are evaluated first for
        # possible ballistic profile to avoid delayed response.
        if 0.01 <= rcs <= 0.5 and speed >= self.ballistic_speed_threshold_mps:
            return RCSClassification.BALLISTIC_TARGET
        if rcs < 0.01:
            return RCSClassification.SMALL_UAV
        if 0.01 <= rcs < 0.1:
            return RCSClassification.MEDIUM_UAV
        if 0.1 <= rcs < 1.0:
            if speed >= self.fighter_speed_threshold_mps:
                return RCSClassification.CRUISE_MISSILE
            return RCSClassification.MEDIUM_UAV
        if 1.0 <= rcs <= 5.0:
            if speed >= self.fighter_speed_threshold_mps:
                return RCSClassification.FIGHTER_AIRCRAFT
            if speed <= self.helicopter_speed_threshold_mps:
                return RCSClassification.HELICOPTER
            return RCSClassification.FIGHTER_AIRCRAFT
        if 5.0 < rcs < 10.0:
            return RCSClassification.HELICOPTER
        if 10.0 <= rcs <= 100.0:
            return RCSClassification.LARGE_AIRCRAFT
        return RCSClassification.UNKNOWN

    def to_target_allocator_label(self, classification: RCSClassification) -> str:
        """Map RCS class to air-defense allocator threat labels."""
        mapping: Dict[RCSClassification, str] = {
            RCSClassification.SMALL_UAV: "ENEMY_UAV",
            RCSClassification.MEDIUM_UAV: "ENEMY_UAV",
            RCSClassification.CRUISE_MISSILE: "ENEMY_CRUISE_MISSILE",
            RCSClassification.HELICOPTER: "ENEMY_AIRCRAFT",
            RCSClassification.FIGHTER_AIRCRAFT: "ENEMY_AIRCRAFT",
            RCSClassification.LARGE_AIRCRAFT: "ENEMY_AIRCRAFT",
            RCSClassification.BALLISTIC_TARGET: "ENEMY_BALLISTIC_TARGET",
            RCSClassification.UNKNOWN: "UNKNOWN",
        }
        return mapping[classification]
