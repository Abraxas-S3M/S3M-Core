"""Interceptor pre-position optimization for predictive engagement windows.

Military context:
The optimizer converts forecasted threat locations into immediate interceptor
flight commands so defenders arrive before swarm ingress.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Tuple

from services.predictive_defense.models import (
    InterceptWindow,
    PrePositionCommand,
    ThreatTrajectoryPrediction,
)


def _distance_m(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


@dataclass
class InterceptorProfile:
    """Operational state required for pre-position timing calculations."""

    interceptor_id: str
    position_m: Tuple[float, float, float]
    max_speed_mps: float
    readiness: float = 1.0

    def __post_init__(self) -> None:
        self.position_m = (float(self.position_m[0]), float(self.position_m[1]), float(self.position_m[2]))
        self.max_speed_mps = max(1.0, float(self.max_speed_mps))
        self.readiness = max(0.0, min(1.0, float(self.readiness)))


class PrePositionOptimizer:
    """Compute predictive interceptor flight commands from threat forecasts."""

    def __init__(
        self,
        arrival_buffer_s: float = 5.0,
        intercept_window_half_width_s: float = 10.0,
    ) -> None:
        self.arrival_buffer_s = max(0.0, float(arrival_buffer_s))
        self.intercept_window_half_width_s = max(1.0, float(intercept_window_half_width_s))

    def optimize(
        self,
        *,
        trajectory_predictions: List[ThreatTrajectoryPrediction],
        interceptor_profiles: List[InterceptorProfile],
        now_s: float,
    ) -> List[PrePositionCommand]:
        """Generate feasible pre-position commands for predicted threat tracks."""
        available = [profile for profile in interceptor_profiles if profile.readiness > 0.2]
        if not available:
            return []

        commands: List[PrePositionCommand] = []
        used_interceptors: set[str] = set()
        prioritized = sorted(trajectory_predictions, key=lambda item: item.risk_score, reverse=True)
        for prediction in prioritized:
            target_solutions = self._select_target_solutions(prediction)
            if not target_solutions:
                continue
            best_profile: Optional[InterceptorProfile] = None
            best_solution: Optional[Tuple[float, Tuple[float, float, float]]] = None
            best_margin = -1e9

            for profile in available:
                if profile.interceptor_id in used_interceptors:
                    continue
                for horizon_s, intercept_point in target_solutions:
                    threat_arrival_s = now_s + horizon_s
                    travel_time_s = _distance_m(profile.position_m, intercept_point) / profile.max_speed_mps
                    arrival_margin_s = (threat_arrival_s - self.arrival_buffer_s) - (now_s + travel_time_s)
                    if arrival_margin_s > best_margin:
                        best_margin = arrival_margin_s
                        best_profile = profile
                        best_solution = (horizon_s, intercept_point)

            if best_profile is None or best_solution is None or best_margin < 0.0:
                continue

            used_interceptors.add(best_profile.interceptor_id)
            horizon_s, intercept_point = best_solution
            threat_arrival_s = now_s + horizon_s
            preferred_intercept_s = threat_arrival_s - self.arrival_buffer_s
            travel_time_s = _distance_m(best_profile.position_m, intercept_point) / best_profile.max_speed_mps
            launch_time_s = max(now_s, preferred_intercept_s - travel_time_s)
            launch_now = launch_time_s <= (now_s + 1e-6)
            window = InterceptWindow(
                threat_id=prediction.track_id,
                start_time_s=preferred_intercept_s - self.intercept_window_half_width_s,
                end_time_s=preferred_intercept_s + self.intercept_window_half_width_s,
                preferred_time_s=preferred_intercept_s,
                intercept_point_m=intercept_point,
                confidence=min(0.99, (prediction.forecast_confidence * 0.7) + (prediction.risk_score * 0.3)),
            )
            commands.append(
                PrePositionCommand(
                    interceptor_id=best_profile.interceptor_id,
                    target_track_id=prediction.track_id,
                    launch_position_m=best_profile.position_m,
                    intercept_point_m=intercept_point,
                    launch_time_s=launch_time_s,
                    intercept_time_s=preferred_intercept_s,
                    intercept_window=window,
                    priority=max(1, int((1.0 - prediction.risk_score) * 100)),
                    launch_now=launch_now,
                )
            )
        return commands

    @staticmethod
    def _select_target_solutions(
        prediction: ThreatTrajectoryPrediction,
    ) -> List[Tuple[float, Tuple[float, float, float]]]:
        # Tactical doctrine: evaluate 60s first, then 120s, then any remaining.
        selected: List[Tuple[float, Tuple[float, float, float]]] = []
        for horizon_s in (60, 120):
            point = prediction.predicted_positions_m.get(horizon_s)
            if point is not None:
                selected.append((float(horizon_s), point))
        for horizon_s in sorted(prediction.predicted_positions_m.keys()):
            if horizon_s in (60, 120):
                continue
            selected.append((float(horizon_s), prediction.predicted_positions_m[horizon_s]))
        return selected
