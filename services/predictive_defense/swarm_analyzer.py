"""Swarm behavior analysis for predictive air-defense cueing.

Military context:
Swarm intent classification helps prioritize finite interceptor inventory
before hostile drones saturate the defended zone.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from services.predictive_defense.models import SwarmPrediction, ThreatTrajectoryPrediction


def _distance_m(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


class SwarmAnalyzer:
    """Detect swarms, estimate convergence, and classify tactical intent."""

    def __init__(
        self,
        min_swarm_size: int = 3,
        cluster_distance_m: float = 5_000.0,
        saturation_threshold: int = 8,
    ) -> None:
        self.min_swarm_size = max(2, int(min_swarm_size))
        self.cluster_distance_m = max(100.0, float(cluster_distance_m))
        self.saturation_threshold = max(self.min_swarm_size, int(saturation_threshold))

    def analyze(
        self,
        trajectory_predictions: List[ThreatTrajectoryPrediction],
        defended_asset_position_m: Tuple[float, float, float],
        defended_asset_name_en: str,
        defended_asset_name_ar: str,
    ) -> List[SwarmPrediction]:
        """Analyze trajectory outputs and return swarm-level predictions."""
        if len(trajectory_predictions) < self.min_swarm_size:
            return []

        seed_points: Dict[str, Tuple[float, float, float]] = {}
        for prediction in trajectory_predictions:
            seed_points[prediction.track_id] = self._primary_position(prediction)

        clusters = self._cluster_predictions(trajectory_predictions, seed_points)
        swarm_predictions: List[SwarmPrediction] = []
        for cluster in clusters:
            if len(cluster) < self.min_swarm_size:
                continue
            member_ids = [item.track_id for item in cluster]
            convergence_point = self._convergence_point(cluster)
            dispersion = self._dispersion(cluster, convergence_point)
            eta_s = self._eta_to_asset(cluster, convergence_point, defended_asset_position_m)
            intent, confidence = self._classify_intent(
                cluster_size=len(cluster),
                eta_to_asset_s=eta_s,
                dispersion_m=dispersion,
            )
            swarm_predictions.append(
                SwarmPrediction(
                    swarm_id=f"swarm-{'-'.join(sorted(member_ids)[:3])}",
                    member_track_ids=member_ids,
                    convergence_point_m=convergence_point,
                    eta_to_asset_s=eta_s,
                    defended_asset_name_en=defended_asset_name_en,
                    defended_asset_name_ar=defended_asset_name_ar,
                    intent_classification=intent,
                    intent_confidence=confidence,
                    threat_count=len(cluster),
                    dispersion_m=dispersion,
                )
            )
        return swarm_predictions

    def _cluster_predictions(
        self,
        trajectory_predictions: List[ThreatTrajectoryPrediction],
        seed_points: Dict[str, Tuple[float, float, float]],
    ) -> List[List[ThreatTrajectoryPrediction]]:
        by_id = {prediction.track_id: prediction for prediction in trajectory_predictions}
        unvisited = set(by_id)
        clusters: List[List[ThreatTrajectoryPrediction]] = []

        while unvisited:
            start_id = unvisited.pop()
            queue = [start_id]
            cluster_ids = {start_id}
            while queue:
                current_id = queue.pop(0)
                current_point = seed_points[current_id]
                neighbors = []
                for candidate_id in list(unvisited):
                    if _distance_m(current_point, seed_points[candidate_id]) <= self.cluster_distance_m:
                        neighbors.append(candidate_id)
                for neighbor_id in neighbors:
                    unvisited.remove(neighbor_id)
                    cluster_ids.add(neighbor_id)
                    queue.append(neighbor_id)
            clusters.append([by_id[track_id] for track_id in cluster_ids])
        return clusters

    @staticmethod
    def _primary_position(prediction: ThreatTrajectoryPrediction) -> Tuple[float, float, float]:
        if 60 in prediction.predicted_positions_m:
            return prediction.predicted_positions_m[60]
        if 120 in prediction.predicted_positions_m:
            return prediction.predicted_positions_m[120]
        if prediction.predicted_positions_m:
            earliest = min(prediction.predicted_positions_m)
            return prediction.predicted_positions_m[earliest]
        return (0.0, 0.0, 0.0)

    def _convergence_point(self, cluster: List[ThreatTrajectoryPrediction]) -> Tuple[float, float, float]:
        points = []
        for prediction in cluster:
            if 120 in prediction.predicted_positions_m:
                points.append(prediction.predicted_positions_m[120])
            else:
                points.append(self._primary_position(prediction))
        x = sum(point[0] for point in points) / len(points)
        y = sum(point[1] for point in points) / len(points)
        z = sum(point[2] for point in points) / len(points)
        return (x, y, z)

    @staticmethod
    def _dispersion(cluster: List[ThreatTrajectoryPrediction], center: Tuple[float, float, float]) -> float:
        distances = []
        for prediction in cluster:
            if not prediction.predicted_positions_m:
                continue
            point = min(
                prediction.predicted_positions_m.values(),
                key=lambda candidate: _distance_m(candidate, center),
            )
            distances.append(_distance_m(point, center))
        if not distances:
            return 0.0
        return sum(distances) / len(distances)

    def _eta_to_asset(
        self,
        cluster: List[ThreatTrajectoryPrediction],
        convergence_point_m: Tuple[float, float, float],
        defended_asset_position_m: Tuple[float, float, float],
    ) -> float:
        distance_to_asset = _distance_m(convergence_point_m, defended_asset_position_m)
        avg_speed = 0.0
        for prediction in cluster:
            if prediction.predicted_speeds_mps:
                avg_speed += max(prediction.predicted_speeds_mps.values())
        avg_speed = avg_speed / max(1, len(cluster))
        if avg_speed <= 0.1:
            avg_speed = 20.0
        return distance_to_asset / avg_speed

    def _classify_intent(self, *, cluster_size: int, eta_to_asset_s: float, dispersion_m: float) -> Tuple[str, float]:
        if cluster_size >= self.saturation_threshold and eta_to_asset_s <= 180.0:
            # Tactical context: dense, fast-closing clusters indicate zone saturation.
            return ("saturation attack", min(0.99, 0.65 + cluster_size / 30.0))
        if cluster_size <= 4 and dispersion_m > (self.cluster_distance_m * 0.75):
            return ("probing", 0.65)
        if dispersion_m > self.cluster_distance_m:
            return ("diversionary", 0.6)
        if eta_to_asset_s > 240.0:
            return ("probing", 0.55)
        return ("diversionary", 0.7)
