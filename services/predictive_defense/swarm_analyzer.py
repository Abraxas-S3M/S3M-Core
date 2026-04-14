"""Swarm behavior analyzer for predictive defense.

Military context:
Infers whether grouped tracks are likely reconnaissance, probing, or strike
formations so posture recommendations can be escalated before impact.
"""

from __future__ import annotations

from math import sqrt
from typing import List, Optional, Tuple

from services.predictive_defense.models import SwarmIntent, SwarmPrediction, ThreatTrajectoryPrediction


def _distance(left: Tuple[float, float, float], right: Tuple[float, float, float]) -> float:
    return sqrt(
        (left[0] - right[0]) * (left[0] - right[0])
        + (left[1] - right[1]) * (left[1] - right[1])
        + (left[2] - right[2]) * (left[2] - right[2])
    )


class SwarmAnalyzer:
    """Analyze group-level trajectory behavior for coordinated threat cues."""

    def analyze(
        self,
        predictions: List[ThreatTrajectoryPrediction],
        defended_position: Tuple[float, float, float],
    ) -> Optional[SwarmPrediction]:
        if len(predictions) < 2:
            return None

        centroid = self._centroid([p.predicted_position for p in predictions])
        dispersion = sum(_distance(p.predicted_position, centroid) for p in predictions) / max(1, len(predictions))
        min_time = min(p.time_to_asset_s for p in predictions)
        centroid_to_asset_m = _distance(centroid, defended_position)
        intent = self._infer_intent(
            track_count=len(predictions),
            dispersion_m=dispersion,
            min_time_s=min_time,
            centroid_to_asset_m=centroid_to_asset_m,
        )
        return SwarmPrediction(
            track_count=len(predictions),
            centroid_position=centroid,
            convergence_time_s=max(0.0, min_time),
            intent=intent,
            dispersion_m=max(0.0, dispersion),
        )

    def _centroid(self, positions: List[Tuple[float, float, float]]) -> Tuple[float, float, float]:
        count = max(1, len(positions))
        return (
            sum(pos[0] for pos in positions) / count,
            sum(pos[1] for pos in positions) / count,
            sum(pos[2] for pos in positions) / count,
        )

    def _infer_intent(
        self,
        *,
        track_count: int,
        dispersion_m: float,
        min_time_s: float,
        centroid_to_asset_m: float,
    ) -> SwarmIntent:
        # Tactical heuristic: dense formations with short convergence to defended
        # assets are treated as probable strike behavior.
        if track_count >= 4 and dispersion_m < 1_500.0 and min_time_s < 180.0:
            return SwarmIntent.STRIKE
        if track_count >= 3 and centroid_to_asset_m < 20_000.0:
            return SwarmIntent.PROBE
        if track_count >= 2:
            return SwarmIntent.RECON
        return SwarmIntent.UNKNOWN
