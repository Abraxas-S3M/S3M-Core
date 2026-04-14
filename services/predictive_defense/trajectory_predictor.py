"""Genome-informed short-horizon trajectory prediction.

Military context:
This predictor biases kinematic hypotheses using known adversary launch
windows, approach bearings, and speed envelopes to enable preemptive defense.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Tuple

from services.predictive_defense.models import ThreatTrajectoryPrediction
from services.predictive_defense.track_genome_bridge import TrackGenomeContext
from src.fusion.threat_genome_correlator import CorrelationVerdict
from src.prediction.confidence_calibrator import ConfidenceCalibrator
from src.prediction.pattern_memory import PatternMemory
from src.prediction.prediction_models import ForecastBundle, ForecastWindow, PredictionHypothesis
from src.prediction.short_horizon_predictor import ShortHorizonPredictor
from src.threat_genome.models import ThreatGenome


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class GenomeAwareTrajectoryPredictor:
    """Fuse kinematic forecasting with threat-genome behavior priors."""

    def __init__(
        self,
        predictor: Optional[ShortHorizonPredictor] = None,
        pattern_memory: Optional[PatternMemory] = None,
        calibrator: Optional[ConfidenceCalibrator] = None,
    ) -> None:
        self.pattern_memory = pattern_memory or PatternMemory()
        if self.pattern_memory.count() == 0:
            self.pattern_memory.register_defaults()
        self.calibrator = calibrator or ConfidenceCalibrator()
        self.predictor = predictor or ShortHorizonPredictor(
            pattern_memory=self.pattern_memory,
            calibrator=self.calibrator,
        )

    def predict(
        self,
        context: TrackGenomeContext,
        correlation_verdict: Optional[CorrelationVerdict] = None,
        matched_genome: Optional[ThreatGenome] = None,
    ) -> ThreatTrajectoryPrediction:
        """Generate a trajectory prediction enhanced by genome behavior priors."""
        bundle = self.predictor.forecast(context.entity_snapshot)
        behavior_bias = self._extract_genome_bias(matched_genome)
        if matched_genome is not None:
            self._apply_genome_bias(bundle=bundle, behavior_bias=behavior_bias, entity_hour=self._entity_hour(context))
        selected_hypothesis = self._pick_selected_hypothesis(bundle)
        predicted_positions, predicted_speeds = self._extract_predictions(bundle)
        genome_confidence = self._genome_confidence(correlation_verdict, matched_genome)
        risk_score = self._risk_score(bundle=bundle, behavior_bias=behavior_bias, genome_confidence=genome_confidence)
        explanation = self._build_explanation(
            bundle=bundle,
            behavior_bias=behavior_bias,
            matched_genome=matched_genome,
            selected_hypothesis=selected_hypothesis.label if selected_hypothesis else "",
        )
        return ThreatTrajectoryPrediction(
            track_id=context.track_id,
            matched_genome_id=self._genome_id(correlation_verdict, matched_genome),
            matched_genome_name=self._genome_name(correlation_verdict, matched_genome),
            matched_genome_confidence=genome_confidence,
            forecast_confidence=bundle.forecast_confidence,
            selected_hypothesis=selected_hypothesis.label if selected_hypothesis else "unknown",
            predicted_positions_m=predicted_positions,
            predicted_speeds_mps=predicted_speeds,
            behavior_context={
                **context.behavior_context,
                "motif_match": bundle.matched_motif_name,
                "motif_match_score": bundle.motif_match_score,
                "genome_bias": behavior_bias,
            },
            risk_score=risk_score,
            explanation=explanation,
        )

    @staticmethod
    def _entity_hour(context: TrackGenomeContext) -> int:
        if context.entity_snapshot.history:
            ts = context.entity_snapshot.history[-1].timestamp_s
            return datetime.fromtimestamp(ts, tz=timezone.utc).hour
        return datetime.now(timezone.utc).hour

    def _apply_genome_bias(self, *, bundle: ForecastBundle, behavior_bias: Dict[str, Any], entity_hour: int) -> None:
        for window in bundle.windows:
            for hypothesis in window.hypotheses:
                bias_multiplier = self._bias_multiplier(
                    heading_deg=hypothesis.predicted_state.heading_deg,
                    speed_mps=hypothesis.predicted_state.speed_mps,
                    entity_hour=entity_hour,
                    behavior_bias=behavior_bias,
                )
                hypothesis.probability = _clamp01(hypothesis.probability * bias_multiplier)
                hypothesis.explanation.factors["genome_bias_multiplier"] = round(bias_multiplier, 4)
                if behavior_bias.get("source"):
                    hypothesis.explanation.evidence.append(f"genome_source={behavior_bias['source']}")
            self._renormalize_window(window)
        if bundle.windows:
            # Tactical context: confidence is recomputed after doctrinal biasing.
            max_probs = [max(h.probability for h in w.hypotheses) for w in bundle.windows if w.hypotheses]
            if max_probs:
                bundle.forecast_confidence = _clamp01(sum(max_probs) / len(max_probs))

    @staticmethod
    def _renormalize_window(window: ForecastWindow) -> None:
        total_prob = sum(h.probability for h in window.hypotheses)
        if total_prob <= 0.0:
            return
        for hypothesis in window.hypotheses:
            hypothesis.probability = hypothesis.probability / total_prob

    @staticmethod
    def _bias_multiplier(
        *,
        heading_deg: float,
        speed_mps: float,
        entity_hour: int,
        behavior_bias: Dict[str, Any],
    ) -> float:
        multiplier = 1.0
        heading_range = behavior_bias.get("heading_range_deg")
        speed_range = behavior_bias.get("speed_range_mps")
        active_hours = behavior_bias.get("active_hours_utc")

        if heading_range:
            if GenomeAwareTrajectoryPredictor._is_heading_in_range(heading_deg, heading_range):
                multiplier *= 1.22
            else:
                multiplier *= 0.84

        if speed_range and isinstance(speed_range, tuple):
            if speed_range[0] <= speed_mps <= speed_range[1]:
                multiplier *= 1.18
            else:
                multiplier *= 0.9

        if active_hours and isinstance(active_hours, tuple):
            if active_hours[0] <= entity_hour <= active_hours[1]:
                multiplier *= 1.12
            else:
                multiplier *= 0.95
        return multiplier

    @staticmethod
    def _is_heading_in_range(heading_deg: float, heading_range: Tuple[float, float]) -> bool:
        low = float(heading_range[0]) % 360.0
        high = float(heading_range[1]) % 360.0
        heading = float(heading_deg) % 360.0
        if low <= high:
            return low <= heading <= high
        return heading >= low or heading <= high

    @staticmethod
    def _pick_selected_hypothesis(bundle: ForecastBundle) -> Optional[PredictionHypothesis]:
        preferred_horizons = [60, 120, 30]
        for horizon in preferred_horizons:
            for window in bundle.windows:
                if int(window.horizon_s) == horizon and window.hypotheses:
                    return max(window.hypotheses, key=lambda hypothesis: hypothesis.probability)
        for window in bundle.windows:
            if window.hypotheses:
                return max(window.hypotheses, key=lambda hypothesis: hypothesis.probability)
        return None

    @staticmethod
    def _extract_predictions(bundle: ForecastBundle) -> Tuple[Dict[int, Tuple[float, float, float]], Dict[int, float]]:
        positions: Dict[int, Tuple[float, float, float]] = {}
        speeds: Dict[int, float] = {}
        for window in bundle.windows:
            horizon = int(window.horizon_s)
            if not window.hypotheses:
                continue
            best = max(window.hypotheses, key=lambda hypothesis: hypothesis.probability)
            positions[horizon] = best.predicted_state.position
            speeds[horizon] = best.predicted_state.speed_mps
        return positions, speeds

    @staticmethod
    def _genome_id(correlation_verdict: Optional[CorrelationVerdict], matched_genome: Optional[ThreatGenome]) -> str:
        if matched_genome is not None:
            return matched_genome.genome_id
        if correlation_verdict and correlation_verdict.matched_genome_id:
            return correlation_verdict.matched_genome_id
        return ""

    @staticmethod
    def _genome_name(correlation_verdict: Optional[CorrelationVerdict], matched_genome: Optional[ThreatGenome]) -> str:
        if matched_genome is not None:
            return matched_genome.actor_name
        if correlation_verdict and correlation_verdict.matched_genome_name:
            return correlation_verdict.matched_genome_name
        return ""

    @staticmethod
    def _genome_confidence(correlation_verdict: Optional[CorrelationVerdict], matched_genome: Optional[ThreatGenome]) -> float:
        if matched_genome is not None:
            return _clamp01(matched_genome.confidence)
        if correlation_verdict is not None:
            return _clamp01(correlation_verdict.composite_score)
        return 0.0

    @staticmethod
    def _risk_score(bundle: ForecastBundle, behavior_bias: Dict[str, Any], genome_confidence: float) -> float:
        speed_bias = 0.0
        speed_range = behavior_bias.get("speed_range_mps")
        if speed_range and isinstance(speed_range, tuple):
            speed_bias = min(0.2, max(speed_range[1] - speed_range[0], 0.0) / 200.0)
        motif_bonus = min(0.15, bundle.motif_match_score * 0.3)
        return _clamp01((bundle.forecast_confidence * 0.5) + (genome_confidence * 0.35) + speed_bias + motif_bonus)

    @staticmethod
    def _build_explanation(
        *,
        bundle: ForecastBundle,
        behavior_bias: Dict[str, Any],
        matched_genome: Optional[ThreatGenome],
        selected_hypothesis: str,
    ) -> List[str]:
        lines = [
            f"Selected hypothesis: {selected_hypothesis}",
            f"Forecast confidence: {bundle.forecast_confidence:.3f}",
            f"Matched motif: {bundle.matched_motif_name or 'none'} ({bundle.motif_match_score:.3f})",
        ]
        if matched_genome is not None:
            lines.append(f"Genome match: {matched_genome.actor_name} ({matched_genome.confidence:.3f})")
        if behavior_bias.get("heading_range_deg"):
            lines.append(f"Genome heading bias: {behavior_bias['heading_range_deg']}")
        if behavior_bias.get("speed_range_mps"):
            lines.append(f"Genome speed bias: {behavior_bias['speed_range_mps']}")
        if behavior_bias.get("active_hours_utc"):
            lines.append(f"Genome temporal bias UTC: {behavior_bias['active_hours_utc']}")
        return lines

    @staticmethod
    def _extract_genome_bias(genome: Optional[ThreatGenome]) -> Dict[str, Any]:
        if genome is None:
            return {}
        heading_range: Optional[Tuple[float, float]] = None
        speed_range: Optional[Tuple[float, float]] = None
        active_hours: Optional[Tuple[int, int]] = None

        for signature in genome.signatures.values():
            movement = signature.movement_patterns or {}
            temporal = signature.temporal_patterns or {}
            if heading_range is None:
                heading_range = GenomeAwareTrajectoryPredictor._extract_heading_range(movement)
            if speed_range is None:
                speed_range = GenomeAwareTrajectoryPredictor._extract_speed_range(movement)
            if active_hours is None:
                active_hours = GenomeAwareTrajectoryPredictor._extract_active_hours(temporal)

        return {
            "source": genome.actor_name,
            "heading_range_deg": heading_range,
            "speed_range_mps": speed_range,
            "active_hours_utc": active_hours,
        }

    @staticmethod
    def _extract_heading_range(movement: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        if "approach_vector_range_deg" in movement and isinstance(movement["approach_vector_range_deg"], (list, tuple)):
            values = movement["approach_vector_range_deg"]
            if len(values) == 2:
                return (float(values[0]), float(values[1]))
        if "bearing_range_deg" in movement and isinstance(movement["bearing_range_deg"], (list, tuple)):
            values = movement["bearing_range_deg"]
            if len(values) == 2:
                return (float(values[0]), float(values[1]))
        if "approach_vector_deg" in movement:
            center = float(movement["approach_vector_deg"])
            return ((center - 10.0) % 360.0, (center + 10.0) % 360.0)
        return None

    @staticmethod
    def _extract_speed_range(movement: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        if "speed_range_mps" in movement and isinstance(movement["speed_range_mps"], (list, tuple)):
            values = movement["speed_range_mps"]
            if len(values) == 2:
                return (float(values[0]), float(values[1]))
        if "speed_min_mps" in movement and "speed_max_mps" in movement:
            return (float(movement["speed_min_mps"]), float(movement["speed_max_mps"]))
        return None

    @staticmethod
    def _extract_active_hours(temporal: Dict[str, Any]) -> Optional[Tuple[int, int]]:
        candidate = temporal.get("active_hours_utc", temporal.get("launch_window_utc"))
        if isinstance(candidate, (list, tuple)) and len(candidate) == 2:
            return (int(candidate[0]), int(candidate[1]))
        return None
