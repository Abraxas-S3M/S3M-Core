"""Trajectory predictor wrapper for predictive defense.

Military context:
Transforms short-horizon branch forecasts into a single actionable estimate
that command-and-control can use for interceptor staging decisions.
"""

from __future__ import annotations

from math import sqrt
from typing import Any, Dict, Optional, Tuple

from services.predictive_defense.models import ThreatTrajectoryPrediction
from src.prediction.prediction_models import EntitySnapshot
from src.prediction.short_horizon_predictor import ShortHorizonPredictor


def _distance(left: Tuple[float, float, float], right: Tuple[float, float, float]) -> float:
    return sqrt(
        (left[0] - right[0]) * (left[0] - right[0])
        + (left[1] - right[1]) * (left[1] - right[1])
        + (left[2] - right[2]) * (left[2] - right[2])
    )


class TrajectoryPredictor:
    """Adapts generic forecast output to defense-specific prediction objects."""

    def __init__(
        self,
        predictor: ShortHorizonPredictor,
        defended_position: Tuple[float, float, float],
        outer_zone_radius_m: float = 40_000.0,
    ) -> None:
        self.predictor = predictor
        self.defended_position = defended_position
        self.outer_zone_radius_m = max(0.0, float(outer_zone_radius_m))

    def predict(
        self,
        entity: EntitySnapshot,
        genome_ctx: Optional[Dict[str, Any]] = None,
    ) -> ThreatTrajectoryPrediction:
        if not isinstance(entity, EntitySnapshot):
            raise ValueError("entity must be EntitySnapshot")

        bundle = self.predictor.forecast(entity)
        best_state = entity.position
        best_horizon_s = 9999.0
        min_distance_m = _distance(entity.position, self.defended_position)

        for window in bundle.windows:
            if not window.hypotheses:
                continue
            top = max(window.hypotheses, key=lambda h: h.probability)
            candidate_distance = _distance(top.predicted_state.position, self.defended_position)
            if candidate_distance < min_distance_m:
                min_distance_m = candidate_distance
                best_state = top.predicted_state.position
                best_horizon_s = max(1.0, float(window.horizon_s))

        current_distance_m = _distance(entity.position, self.defended_position)
        closing_distance_m = max(0.0, current_distance_m - min_distance_m)
        approach_speed_mps = closing_distance_m / max(1.0, best_horizon_s)

        if min_distance_m <= self.outer_zone_radius_m:
            time_to_asset_s = best_horizon_s
        elif approach_speed_mps > 0.0:
            time_to_asset_s = current_distance_m / approach_speed_mps
        else:
            time_to_asset_s = 9_999.0

        genome_name = self._extract_genome_name(genome_ctx)
        risk_score = self._risk_score(
            min_distance_m=min_distance_m,
            time_to_asset_s=time_to_asset_s,
            confidence=bundle.forecast_confidence,
            has_genome_match=genome_name is not None,
        )

        return ThreatTrajectoryPrediction(
            track_id=entity.entity_id,
            predicted_position=best_state,
            time_to_asset_s=max(0.0, time_to_asset_s),
            distance_to_asset_m=max(0.0, min_distance_m),
            approach_speed_mps=max(0.0, approach_speed_mps),
            confidence=max(0.0, min(1.0, bundle.forecast_confidence)),
            genome_match=genome_name,
            risk_score=risk_score,
        )

    def _extract_genome_name(self, genome_ctx: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(genome_ctx, dict):
            return None
        for key in ("match_name", "genome_name", "actor_name", "genome_id"):
            value = genome_ctx.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _risk_score(
        self,
        *,
        min_distance_m: float,
        time_to_asset_s: float,
        confidence: float,
        has_genome_match: bool,
    ) -> float:
        # Tactical scoring: confidence and short timelines should dominate
        # to bias the system toward early interceptor positioning.
        distance_factor = max(0.0, min(1.0, 1.0 - (min_distance_m / max(1.0, self.outer_zone_radius_m))))
        time_factor = max(0.0, min(1.0, 1.0 - (time_to_asset_s / 600.0)))
        genome_factor = 0.15 if has_genome_match else 0.0
        score = (0.45 * time_factor) + (0.30 * distance_factor) + (0.25 * max(0.0, min(1.0, confidence)))
        return max(0.0, min(1.0, score + genome_factor))
