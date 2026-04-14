"""Pre-position optimizer for interceptor staging.

Military context:
Generates deterministic staging commands so interceptor drones can establish
forward geometry before hostile tracks reach defended assets.
"""

from __future__ import annotations

from math import sqrt
from typing import Any, Dict, List, Tuple

from services.predictive_defense.models import PrePositionCommand, SwarmPrediction, ThreatTrajectoryPrediction


def _distance(left: Tuple[float, float, float], right: Tuple[float, float, float]) -> float:
    return sqrt(
        (left[0] - right[0]) * (left[0] - right[0])
        + (left[1] - right[1]) * (left[1] - right[1])
        + (left[2] - right[2]) * (left[2] - right[2])
    )


def _as_xyz(raw_position: Any) -> Tuple[float, float, float]:
    if not isinstance(raw_position, (tuple, list)) or len(raw_position) != 3:
        raise ValueError("interceptor position must be a 3D tuple/list")
    return (float(raw_position[0]), float(raw_position[1]), float(raw_position[2]))


class PrePositionOptimizer:
    """Compute interceptor pre-position commands from predicted threats."""

    def __init__(
        self,
        interceptor_speed_mps: float,
        defended_position: Tuple[float, float, float],
    ) -> None:
        self.interceptor_speed_mps = max(1.0, float(interceptor_speed_mps))
        self.defended_position = (
            float(defended_position[0]),
            float(defended_position[1]),
            float(defended_position[2]),
        )

    def optimize_preposition(
        self,
        predictions: List[ThreatTrajectoryPrediction],
        interceptors: List[Dict[str, Any]],
        swarm: SwarmPrediction | None = None,
    ) -> List[PrePositionCommand]:
        if not predictions or not interceptors:
            return []

        sorted_predictions = sorted(predictions, key=lambda p: (p.time_to_asset_s, -p.risk_score))
        available = [i for i in interceptors if self._is_ready(i)]
        if not available:
            return []

        commands: List[PrePositionCommand] = []
        for prediction, interceptor in zip(sorted_predictions, available):
            interceptor_id = str(interceptor.get("interceptor_id") or interceptor.get("id") or "").strip()
            if not interceptor_id:
                continue
            try:
                interceptor_position = _as_xyz(interceptor.get("position", self.defended_position))
            except (TypeError, ValueError):
                continue

            stage = self._stage_position(prediction.predicted_position)
            eta_s = _distance(interceptor_position, stage) / self.interceptor_speed_mps
            launch_now = prediction.time_to_asset_s <= (eta_s + 20.0)
            rationale = (
                f"Track {prediction.track_id} ETA {prediction.time_to_asset_s:.0f}s, "
                f"stage ETA {eta_s:.0f}s"
            )
            if swarm is not None:
                rationale += f", swarm intent={swarm.intent.value}"

            commands.append(
                PrePositionCommand(
                    interceptor_id=interceptor_id,
                    target_track_id=prediction.track_id,
                    staging_position=stage,
                    eta_s=max(0.0, eta_s),
                    launch_now=launch_now,
                    rationale=rationale,
                )
            )
        return commands

    def _stage_position(self, threat_position: Tuple[float, float, float]) -> Tuple[float, float, float]:
        # Tactical geometry: stage halfway between defended asset and predicted
        # threat location to preserve interception optionality.
        return (
            self.defended_position[0] + ((threat_position[0] - self.defended_position[0]) * 0.5),
            self.defended_position[1] + ((threat_position[1] - self.defended_position[1]) * 0.5),
            self.defended_position[2] + ((threat_position[2] - self.defended_position[2]) * 0.5),
        )

    def _is_ready(self, interceptor: Dict[str, Any]) -> bool:
        status = str(interceptor.get("status", "ready")).strip().lower()
        ready_flag = interceptor.get("ready", True)
        return bool(ready_flag) and status in {"ready", "available", "idle"}
