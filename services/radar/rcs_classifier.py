"""RCS-based aerial target classification.

Military context:
The Krechet classifies detected targets by their radar cross-section to
determine the appropriate effector type and engagement priority. A 0.01 m²
return is likely a small UAV, while 5 m² is likely a manned aircraft.
This classification feeds directly into the air defense TargetAllocator.
"""

from __future__ import annotations

from typing import List, Tuple

from services.radar.models import RCSClassification, RadarPlot


# (min_rcs_m2, max_rcs_m2, classification, base_confidence)
RCS_CLASSIFICATION_TABLE: List[Tuple[float, float, RCSClassification, float]] = [
    (0.0, 0.001, RCSClassification.CLUTTER, 0.40),
    (0.001, 0.01, RCSClassification.SMALL_UAV, 0.65),
    (0.01, 0.1, RCSClassification.MEDIUM_UAV, 0.70),
    (0.1, 1.0, RCSClassification.LARGE_UAV, 0.55),  # Ambiguous: could be cruise missile
    (0.1, 1.0, RCSClassification.CRUISE_MISSILE, 0.50),  # Overlap region
    (1.0, 5.0, RCSClassification.FIGHTER, 0.60),
    (1.0, 10.0, RCSClassification.HELICOPTER, 0.55),
    (10.0, 100.0, RCSClassification.LARGE_AIRCRAFT, 0.70),
    (0.01, 0.5, RCSClassification.BALLISTIC, 0.40),
]

# Speed-based disambiguation for overlapping RCS bands (m/s)
SPEED_HINTS = {
    RCSClassification.SMALL_UAV: (0, 60),
    RCSClassification.MEDIUM_UAV: (20, 120),
    RCSClassification.LARGE_UAV: (30, 80),
    RCSClassification.CRUISE_MISSILE: (150, 350),
    RCSClassification.HELICOPTER: (0, 90),
    RCSClassification.FIGHTER: (100, 700),
    RCSClassification.LARGE_AIRCRAFT: (50, 300),
    RCSClassification.BALLISTIC: (200, 3000),
}


class RCSClassifier:
    """Classify aerial targets by radar cross-section and kinematics."""

    def __init__(self) -> None:
        self.table = list(RCS_CLASSIFICATION_TABLE)
        self.speed_hints = dict(SPEED_HINTS)

    def classify(
        self,
        rcs_m2: float,
        speed_mps: float = 0.0,
        altitude_m: float = 0.0,
    ) -> Tuple[RCSClassification, float]:
        """Classify a target and return (classification, confidence).

        Uses RCS as primary discriminant, with speed and altitude as
        disambiguation factors when RCS bands overlap.
        """
        if rcs_m2 <= 0:
            return (RCSClassification.CLUTTER, 0.3)

        candidates: List[Tuple[RCSClassification, float]] = []
        for min_rcs, max_rcs, cls, base_conf in self.table:
            if min_rcs <= rcs_m2 < max_rcs:
                conf = base_conf
                # Speed disambiguation
                if speed_mps > 0 and cls in self.speed_hints:
                    min_spd, max_spd = self.speed_hints[cls]
                    if min_spd <= speed_mps <= max_spd:
                        conf += 0.15
                    elif speed_mps > max_spd * 1.5 or speed_mps < min_spd * 0.5:
                        conf -= 0.20
                # Altitude hints
                if altitude_m > 10000 and cls in {
                    RCSClassification.SMALL_UAV,
                    RCSClassification.HELICOPTER,
                }:
                    conf -= 0.15  # Small UAVs and helicopters rarely fly > 10km
                if altitude_m < 100 and cls == RCSClassification.LARGE_AIRCRAFT:
                    conf -= 0.10  # Large aircraft rarely at very low altitude
                candidates.append((cls, max(0.1, min(0.95, conf))))

        if not candidates:
            return (RCSClassification.UNKNOWN, 0.3)

        # Return highest confidence candidate
        candidates.sort(key=lambda c: c[1], reverse=True)
        return candidates[0]

    def classify_plot(self, plot: RadarPlot) -> RadarPlot:
        """Classify a RadarPlot in-place using its RCS and velocity."""
        altitude = plot.position_cartesian[2] if plot.position_cartesian else 0.0
        cls, conf = self.classify(
            plot.rcs_linear_m2,
            abs(plot.radial_velocity_mps),
            altitude,
        )
        plot.rcs_classification = cls
        plot.classification_confidence = conf
        return plot

    def classify_plots(self, plots: List[RadarPlot]) -> List[RadarPlot]:
        """Batch classify multiple plots."""
        return [self.classify_plot(p) for p in plots]

    @staticmethod
    def rcs_class_to_threat_class(rcs_class: RCSClassification) -> str:
        """Map RCS classification to kill-chain/air-defense target classification."""
        mapping = {
            RCSClassification.SMALL_UAV: "ENEMY_UAV",
            RCSClassification.MEDIUM_UAV: "ENEMY_UAV",
            RCSClassification.LARGE_UAV: "ENEMY_UAV",
            RCSClassification.CRUISE_MISSILE: "ENEMY_CRUISE_MISSILE",
            RCSClassification.HELICOPTER: "ENEMY_HELICOPTER",
            RCSClassification.FIGHTER: "ENEMY_AIRCRAFT",
            RCSClassification.LARGE_AIRCRAFT: "ENEMY_AIRCRAFT",
            RCSClassification.BALLISTIC: "ENEMY_BALLISTIC",
            RCSClassification.CLUTTER: "CLUTTER",
            RCSClassification.UNKNOWN: "UNKNOWN",
        }
        return mapping.get(rcs_class, "UNKNOWN")
