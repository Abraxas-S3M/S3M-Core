"""Interceptor pre-positioning optimizer.

Military context:
Given predicted threat positions at T+60/120s, this optimizer computes
where and when to launch interceptor drones so they arrive at the
predicted intercept point simultaneously with or before the threats.
This is the operational advantage: instead of reacting when targets
enter the defense zone, S3M pre-positions interceptors on predicted
approach corridors 60-120 seconds early.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from services.predictive_defense.models import (
    InterceptWindow,
    PrePositionCommand,
    SwarmPrediction,
    ThreatTrajectoryPrediction,
)


class PrePositionOptimizer:
    """Compute optimal interceptor pre-positioning from threat predictions."""

    def __init__(
        self,
        interceptor_speed_mps: float = 60.0,
        interceptor_launch_delay_s: float = 15.0,
        defended_position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        min_engagement_window_s: float = 20.0,
    ) -> None:
        self.interceptor_speed = float(interceptor_speed_mps)
        self.launch_delay = float(interceptor_launch_delay_s)
        self.defended_position = self._validate_position(defended_position, "defended_position")
        self.min_engagement_window = float(min_engagement_window_s)

        if not math.isfinite(self.interceptor_speed) or self.interceptor_speed <= 0.0:
            raise ValueError("interceptor_speed_mps must be a finite positive value")
        if not math.isfinite(self.launch_delay) or self.launch_delay < 0.0:
            raise ValueError("interceptor_launch_delay_s must be a finite non-negative value")
        if not math.isfinite(self.min_engagement_window) or self.min_engagement_window < 0.0:
            raise ValueError("min_engagement_window_s must be a finite non-negative value")

    def compute_intercept_window(
        self,
        prediction: ThreatTrajectoryPrediction,
        interceptor_position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> InterceptWindow:
        """Compute the time/space window where an intercept is possible."""
        intc_pos = self._validate_position(interceptor_position, "interceptor_position")

        # Prioritize longer-horizon position to exploit tactical pre-positioning time.
        intercept_pos = prediction.predicted_60s or prediction.predicted_30s or prediction.current_position
        return self._compute_window_for_position(prediction, intc_pos, intercept_pos)

    def optimize_preposition(
        self,
        predictions: List[ThreatTrajectoryPrediction],
        available_interceptors: List[Dict],
        swarm: Optional[SwarmPrediction] = None,
    ) -> List[PrePositionCommand]:
        """Compute pre-position commands for available interceptors."""
        commands: List[PrePositionCommand] = []

        # Sort predictions by urgency (closest arrival first).
        sorted_preds = sorted(predictions, key=lambda p: p.time_to_asset_s)

        for i, pred in enumerate(sorted_preds):
            if i >= len(available_interceptors):
                break

            intc = available_interceptors[i]
            intc_id = str(intc.get("interceptor_id", f"intc-{i}"))
            intc_pos = self._validate_position(
                intc.get("position", self.defended_position),
                f"available_interceptors[{i}].position",
            )

            window = self.compute_intercept_window(pred, intc_pos)
            engagement_time = window.window_end_s - window.window_start_s

            # If the initial station point is infeasible, retry a closer 30s forecast.
            if engagement_time < self.min_engagement_window and pred.predicted_30s:
                window = self._compute_window_for_position(pred, intc_pos, pred.predicted_30s)

            launch_offset = max(0.0, window.optimal_launch_s)
            launch_now = launch_offset < 5.0  # Execute immediate scramble when margin is minimal.

            # Place the loiter point slightly inward toward defended assets to reduce terminal dash.
            prepos = self._compute_preposition_point(window.intercept_position)

            reasoning = (
                f"Pre-position {intc_id} at predicted intercept point "
                f"({prepos[0]:.0f}, {prepos[1]:.0f}, {prepos[2]:.0f}) "
                f"for track {pred.track_id}"
            )
            if pred.genome_match:
                reasoning += f" (genome: {pred.genome_match})"
            if swarm:
                reasoning += f" | Swarm of {swarm.track_count}, intent: {swarm.intent.value}"

            cmd = PrePositionCommand(
                interceptor_id=intc_id,
                target_track_id=pred.track_id,
                launch_now=launch_now,
                intercept_position=prepos,
                loiter_altitude_m=prepos[2],
                launch_time_offset_s=launch_offset,
                time_to_station_s=window.window_start_s,
                engagement_window_s=max(0.0, window.window_end_s - window.window_start_s),
                reasoning=reasoning,
                confidence=max(0.0, min(1.0, pred.prediction_confidence * window.closing_geometry_score)),
            )
            commands.append(cmd)

        return commands

    def _compute_window_for_position(
        self,
        prediction: ThreatTrajectoryPrediction,
        interceptor_position: Tuple[float, float, float],
        intercept_pos: Tuple[float, float, float],
    ) -> InterceptWindow:
        dist_to_intercept = self._distance(interceptor_position, intercept_pos)
        time_to_station = self.launch_delay + dist_to_intercept / self.interceptor_speed
        window_start = time_to_station
        window_end = max(window_start, prediction.time_to_asset_s)

        threat_bearing = prediction.current_heading_deg
        intercept_bearing = self._bearing_from_to(interceptor_position, intercept_pos)
        angle_off = abs(threat_bearing - intercept_bearing)
        if angle_off > 180.0:
            angle_off = 360.0 - angle_off
        geometry_score = max(0.1, 1.0 - angle_off / 180.0)

        return InterceptWindow(
            window_start_s=window_start,
            window_end_s=window_end,
            optimal_launch_s=max(0.0, window_start - self.launch_delay),
            intercept_position=intercept_pos,
            intercept_altitude_m=intercept_pos[2],
            closing_geometry_score=geometry_score,
        )

    def _compute_preposition_point(
        self,
        intercept_pos: Tuple[float, float, float],
    ) -> Tuple[float, float, float]:
        """Position interceptor slightly toward the defended asset from intercept point."""
        offset_ratio = 0.2
        x = intercept_pos[0] + (self.defended_position[0] - intercept_pos[0]) * offset_ratio
        y = intercept_pos[1] + (self.defended_position[1] - intercept_pos[1]) * offset_ratio
        z = intercept_pos[2]
        return (x, y, z)

    @staticmethod
    def _validate_position(position: Any, field_name: str) -> Tuple[float, float, float]:
        if not isinstance(position, (list, tuple)):
            raise ValueError(f"{field_name} must be a 3D list/tuple")
        if len(position) != 3:
            raise ValueError(f"{field_name} must contain exactly 3 coordinates")
        x, y, z = float(position[0]), float(position[1]), float(position[2])
        if not all(math.isfinite(v) for v in (x, y, z)):
            raise ValueError(f"{field_name} coordinates must be finite values")
        return (x, y, z)

    @staticmethod
    def _distance(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    @staticmethod
    def _bearing_from_to(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        return math.degrees(math.atan2(dx, dy)) % 360.0
