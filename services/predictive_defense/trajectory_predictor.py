"""Genome-enhanced threat trajectory prediction.

Military context:
This is the predictive advantage. When a radar track matches a known
threat genome (e.g., Houthi drone program), this predictor biases the
kinematic forecast with behavioral patterns from that genome: expected
approach vectors, speed profiles, altitude preferences, and temporal
patterns. The result is a trajectory prediction that accounts for
adversary doctrine, not just physics.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from services.predictive_defense.models import ThreatTrajectoryPrediction
from src.prediction.prediction_models import EntitySnapshot, ForecastBundle
from src.prediction.short_horizon_predictor import ShortHorizonPredictor


Position3D = Tuple[float, float, float]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    return numeric


def _normalize_position(position: Position3D, *, field_name: str) -> Position3D:
    if len(position) != 3:
        raise ValueError(f"{field_name} must contain exactly three coordinates")
    x, y, z = (float(position[0]), float(position[1]), float(position[2]))
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        raise ValueError(f"{field_name} coordinates must be finite numbers")
    return (x, y, z)


class TrajectoryPredictor:
    """Produce genome-biased trajectory predictions for threat tracks."""

    def __init__(
        self,
        predictor: Optional[ShortHorizonPredictor] = None,
        defended_position: Position3D = (0.0, 0.0, 0.0),
        outer_zone_radius_m: float = 40000.0,
    ) -> None:
        self.predictor = predictor or ShortHorizonPredictor(windows_s=[30.0, 60.0, 120.0])
        self.defended_position = _normalize_position(
            defended_position,
            field_name="defended_position",
        )
        self.outer_zone_radius_m = _safe_float(outer_zone_radius_m, 40000.0)
        if self.outer_zone_radius_m < 0.0:
            raise ValueError("outer_zone_radius_m must be non-negative")

    def predict(
        self,
        entity: EntitySnapshot,
        genome_context: Optional[Dict[str, Any]] = None,
    ) -> ThreatTrajectoryPrediction:
        """Predict trajectory with optional genome behavioral bias."""
        bundle = self.predictor.forecast(entity)
        positions = self._extract_positions(bundle)

        genome_bias_applied = False
        genome_match: Optional[str] = None
        genome_confidence = 0.0
        behavioral_pattern = ""

        if isinstance(genome_context, dict):
            genome_match_raw = genome_context.get("actor_name")
            genome_match = str(genome_match_raw) if genome_match_raw is not None else None
            genome_confidence = _clamp(_safe_float(genome_context.get("confidence"), 0.0), 0.0, 1.0)
            behavioral_pattern_raw = genome_context.get("behavioral_pattern", "")
            behavioral_pattern = str(behavioral_pattern_raw)

            approach_bearing = _safe_float(genome_context.get("approach_bearing"), float("nan"))
            speed_range = self._coerce_speed_range(genome_context.get("speed_range_mps"))

            if math.isfinite(approach_bearing):
                positions = self._apply_bearing_bias(
                    positions=positions,
                    entity=entity,
                    genome_bearing=approach_bearing,
                    confidence=genome_confidence,
                )
                genome_bias_applied = True

            if speed_range is not None:
                positions = self._apply_speed_bias(
                    positions=positions,
                    entity=entity,
                    speed_range=speed_range,
                    confidence=genome_confidence,
                )
                genome_bias_applied = True

        range_now = self._distance(entity.position, self.defended_position)
        pos_30 = positions.get("30")
        pos_60 = positions.get("60")
        pos_120 = positions.get("120")
        range_30 = self._distance(pos_30, self.defended_position) if pos_30 is not None else range_now
        range_60 = self._distance(pos_60, self.defended_position) if pos_60 is not None else range_now
        range_120 = self._distance(pos_120, self.defended_position) if pos_120 is not None else range_now

        if range_60 < range_now:
            closing_speed = max(1.0, (range_now - range_60) / 60.0)
        else:
            closing_speed = max(1.0, _safe_float(entity.speed_mps, 0.0))

        time_to_asset = range_now / closing_speed if closing_speed > 0.0 else 9999.0
        time_to_zone = max(0.0, range_now - self.outer_zone_radius_m) / closing_speed if closing_speed > 0.0 else 9999.0

        base_confidence = self._bundle_confidence(bundle)
        if genome_bias_applied:
            prediction_confidence = base_confidence * 0.5 + genome_confidence * 0.5
        else:
            prediction_confidence = base_confidence

        return ThreatTrajectoryPrediction(
            track_id=entity.entity_id,
            target_classification=entity.entity_type,
            genome_match=genome_match,
            genome_confidence=genome_confidence,
            current_position=entity.position,
            current_velocity=(
                entity.speed_mps * math.sin(math.radians(entity.heading_deg)),
                entity.speed_mps * math.cos(math.radians(entity.heading_deg)),
                0.0,
            ),
            current_speed_mps=entity.speed_mps,
            current_heading_deg=entity.heading_deg,
            predicted_30s=pos_30,
            predicted_60s=pos_60,
            predicted_120s=pos_120,
            range_to_asset_now_m=range_now,
            range_to_asset_30s_m=range_30,
            range_to_asset_60s_m=range_60,
            range_to_asset_120s_m=range_120,
            time_to_zone_entry_s=max(0.0, time_to_zone),
            time_to_asset_s=time_to_asset,
            prediction_confidence=_clamp(prediction_confidence, 0.0, 1.0),
            genome_bias_applied=genome_bias_applied,
            behavioral_pattern=behavioral_pattern,
        )

    def _extract_positions(self, bundle: ForecastBundle) -> Dict[str, Position3D]:
        positions: Dict[str, Position3D] = {}
        for window in bundle.windows:
            if not window.hypotheses:
                continue
            best = max(window.hypotheses, key=lambda hypothesis: hypothesis.probability)
            key = str(int(window.horizon_s))
            positions[key] = best.predicted_state.position
        return positions

    def _apply_bearing_bias(
        self,
        positions: Dict[str, Position3D],
        entity: EntitySnapshot,
        genome_bearing: float,
        confidence: float,
    ) -> Dict[str, Position3D]:
        """Blend predicted positions toward the genome's expected approach bearing."""
        bias_weight = _clamp(confidence, 0.0, 1.0) * 0.3
        blended_heading = entity.heading_deg * (1.0 - bias_weight) + genome_bearing * bias_weight
        blended_rad = math.radians(blended_heading)

        biased_positions: Dict[str, Position3D] = dict(positions)
        for key, pos in positions.items():
            horizon = _safe_float(key, 0.0)
            if horizon <= 0.0:
                continue
            distance = entity.speed_mps * horizon
            biased_pos = (
                entity.position[0] + distance * math.sin(blended_rad),
                entity.position[1] + distance * math.cos(blended_rad),
                pos[2],
            )
            biased_positions[key] = (
                pos[0] * (1.0 - bias_weight) + biased_pos[0] * bias_weight,
                pos[1] * (1.0 - bias_weight) + biased_pos[1] * bias_weight,
                pos[2],
            )
        return biased_positions

    def _apply_speed_bias(
        self,
        positions: Dict[str, Position3D],
        entity: EntitySnapshot,
        speed_range: Tuple[float, float],
        confidence: float,
    ) -> Dict[str, Position3D]:
        """Adjust predicted speed toward genome's known speed profile."""
        genome_avg_speed = (speed_range[0] + speed_range[1]) / 2.0
        bias_weight = _clamp(confidence, 0.0, 1.0) * 0.2
        biased_speed = entity.speed_mps * (1.0 - bias_weight) + genome_avg_speed * bias_weight
        speed_ratio = biased_speed / max(entity.speed_mps, 0.1)

        biased_positions: Dict[str, Position3D] = dict(positions)
        for key, pos in positions.items():
            dx = pos[0] - entity.position[0]
            dy = pos[1] - entity.position[1]
            biased_positions[key] = (
                entity.position[0] + dx * speed_ratio,
                entity.position[1] + dy * speed_ratio,
                pos[2],
            )
        return biased_positions

    @staticmethod
    def _coerce_speed_range(value: Any) -> Optional[Tuple[float, float]]:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        low = _safe_float(value[0], float("nan"))
        high = _safe_float(value[1], float("nan"))
        if not (math.isfinite(low) and math.isfinite(high)):
            return None
        minimum = min(low, high)
        maximum = max(low, high)
        if minimum < 0.0:
            return None
        return (minimum, maximum)

    @staticmethod
    def _bundle_confidence(bundle: ForecastBundle) -> float:
        raw = getattr(bundle, "overall_confidence", None)
        if raw is None:
            raw = getattr(bundle, "forecast_confidence", 0.5)
        return _clamp(_safe_float(raw, 0.5), 0.0, 1.0)

    @staticmethod
    def _distance(a: Position3D, b: Position3D) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)
