"""Swarm detection and convergence prediction.

Military context:
Detects when multiple threat tracks form a coordinated attack formation,
predicts their convergence point on the defended asset, and classifies
the attack intent. A saturation attack with 16 Shaheds converging from
the same bearing at staggered intervals looks very different from a
diversionary probe with 3 drones from opposite bearings.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from services.predictive_defense.models import SwarmIntent, SwarmPrediction, ThreatTrajectoryPrediction


class SwarmAnalyzer:
    """Analyze multiple threat predictions for swarm behavior."""

    def __init__(
        self,
        min_swarm_size: int = 3,
        bearing_cluster_deg: float = 45.0,
        speed_cluster_mps: float = 20.0,
    ) -> None:
        if int(min_swarm_size) <= 0:
            raise ValueError("min_swarm_size must be positive")
        if not math.isfinite(float(bearing_cluster_deg)) or float(bearing_cluster_deg) <= 0.0:
            raise ValueError("bearing_cluster_deg must be a positive finite value")
        if not math.isfinite(float(speed_cluster_mps)) or float(speed_cluster_mps) < 0.0:
            raise ValueError("speed_cluster_mps must be a finite non-negative value")
        self.min_swarm_size = int(min_swarm_size)
        self.bearing_cluster_deg = float(bearing_cluster_deg)
        self.speed_cluster_mps = float(speed_cluster_mps)

    def analyze(
        self,
        predictions: List[ThreatTrajectoryPrediction],
        defended_position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> Optional[SwarmPrediction]:
        """Detect swarm behavior and predict convergence."""
        defended_position = self._validate_xyz(defended_position, "defended_position")
        if not isinstance(predictions, list):
            raise ValueError("predictions must be a list")
        if any(not isinstance(pred, ThreatTrajectoryPrediction) for pred in predictions):
            raise ValueError("predictions must only contain ThreatTrajectoryPrediction values")
        if len(predictions) < self.min_swarm_size:
            return None

        # Tactical geometry: bearing from each track to defended asset.
        bearings = []
        speeds = []
        for pred in predictions:
            dx = defended_position[0] - pred.current_position[0]
            dy = defended_position[1] - pred.current_position[1]
            bearing = math.degrees(math.atan2(dx, dy)) % 360.0
            bearings.append(bearing)
            speeds.append(pred.current_speed_mps)

        # Check bearing clustering
        mean_bearing = self._circular_mean(bearings)
        bearing_spread = max(self._circular_deviation(bearings, mean_bearing), 0.1)
        speed_spread = max(speeds) - min(speeds) if speeds else 0.0

        is_clustered = bearing_spread < self.bearing_cluster_deg and speed_spread < self.speed_cluster_mps
        if not is_clustered:
            return None

        # Convergence point: average of predicted_60s positions or fallback to current tracks.
        convergence_positions = [p.predicted_60s for p in predictions if p.predicted_60s is not None]
        if not convergence_positions:
            convergence_positions = [p.current_position for p in predictions]

        conv_x = sum(p[0] for p in convergence_positions) / len(convergence_positions)
        conv_y = sum(p[1] for p in convergence_positions) / len(convergence_positions)
        conv_z = sum(p[2] for p in convergence_positions) / len(convergence_positions)

        spread = max(
            math.sqrt((p[0] - conv_x) ** 2 + (p[1] - conv_y) ** 2)
            for p in convergence_positions
        )

        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
        arrival_times = sorted(p.time_to_asset_s for p in predictions if p.time_to_asset_s > 0.0)

        # Classify intent
        intent = self._classify_intent(
            len(predictions),
            bearing_spread,
            speed_spread,
            arrival_times,
            spread,
        )

        # Estimate defense Pk against this swarm
        effectors_needed = max(1, len(predictions))
        single_pk = 0.65  # Base Pk per engagement
        overall_pk = 1.0 - (1.0 - single_pk) ** min(effectors_needed, len(predictions))

        return SwarmPrediction(
            track_ids=[p.track_id for p in predictions],
            track_count=len(predictions),
            intent=intent,
            convergence_point=(conv_x, conv_y, conv_z),
            convergence_spread_m=spread,
            convergence_time_s=arrival_times[len(arrival_times) // 2] if arrival_times else 0.0,
            approach_bearing_deg=mean_bearing,
            average_speed_mps=avg_speed,
            first_arrival_s=arrival_times[0] if arrival_times else 0.0,
            last_arrival_s=arrival_times[-1] if arrival_times else 0.0,
            wave_spacing_s=(
                (arrival_times[-1] - arrival_times[0]) / max(1, len(arrival_times) - 1)
                if len(arrival_times) > 1
                else 0.0
            ),
            estimated_pk_defense=overall_pk,
            effectors_required=effectors_needed,
            genome_match=predictions[0].genome_match if predictions else None,
        )

    def _classify_intent(
        self,
        count: int,
        bearing_spread: float,
        speed_spread: float,
        arrival_times: List[float],
        spatial_spread: float,
    ) -> SwarmIntent:
        _ = speed_spread  # Reserved for future doctrine-specific spread thresholds.
        if count >= 8 and bearing_spread < 30.0:
            return SwarmIntent.SATURATION
        if count <= 4 and spatial_spread > 5000.0:
            return SwarmIntent.PROBING
        if len(arrival_times) > 1:
            spacing = (arrival_times[-1] - arrival_times[0]) / max(1, len(arrival_times) - 1)
            if spacing > 30.0:
                return SwarmIntent.SEQUENTIAL
        if bearing_spread > 90.0:
            return SwarmIntent.DIVERSIONARY
        return SwarmIntent.UNKNOWN

    @staticmethod
    def _circular_mean(angles: List[float]) -> float:
        if not angles:
            return 0.0
        sin_sum = sum(math.sin(math.radians(a)) for a in angles)
        cos_sum = sum(math.cos(math.radians(a)) for a in angles)
        return math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0

    @staticmethod
    def _circular_deviation(angles: List[float], mean: float) -> float:
        if not angles:
            return 0.0
        diffs = []
        for angle in angles:
            delta = abs(angle - mean)
            if delta > 180.0:
                delta = 360.0 - delta
            diffs.append(delta)
        return max(diffs) if diffs else 0.0

    @staticmethod
    def _validate_xyz(value: Tuple[float, float, float], field_name: str) -> Tuple[float, float, float]:
        if not isinstance(value, tuple) or len(value) != 3:
            raise ValueError(f"{field_name} must be a 3-tuple")
        x = float(value[0])
        y = float(value[1])
        z = float(value[2])
        if not math.isfinite(x) or not math.isfinite(y) or not math.isfinite(z):
            raise ValueError(f"{field_name} must contain finite coordinates")
        return (x, y, z)
