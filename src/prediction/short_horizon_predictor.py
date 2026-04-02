# File: src/prediction/short_horizon_predictor.py
"""Short-horizon operational prediction engine for S3M.

Forecasts what an entity is likely to do over configurable time windows
(30s, 2min, 10min) using four layered algorithms:

  1. Kinematic extrapolation: linear projection with uncertainty cone
  2. Behavioral trend analysis: detect escalation/stability from history
  3. Multi-hypothesis branching: generate tactical alternatives
  4. Volatility-scaled uncertainty: erratic entities get wider bounds

This is defensive decision-support — it predicts what threats and contacts
WILL do, not what WE should do.  No offensive planning.

Usage::

    predictor = ShortHorizonPredictor()
    bundle = predictor.forecast(entity_snapshot)
    # or
    bundle = predictor.forecast_from_request(prediction_request)
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .prediction_models import (
    CoordinationIndicator,
    EntitySnapshot,
    ExplanationBlock,
    ForecastBundle,
    HistoryPoint,
    MovementMode,
    PredictedEntityState,
    PredictionHypothesis,
    PredictionRequest,
    PredictionWindow,
    ThreatPosture,
    UncertaintyEstimate,
    _variance,
)


# =====================================================================
# Threat level numeric mapping for trend analysis
# =====================================================================

_THREAT_RANK: Dict[str, int] = {
    "negligible": 1, "low": 2, "medium": 3, "high": 4, "critical": 5, "unknown": 0,
}

_RANK_THREAT: Dict[int, str] = {v: k for k, v in _THREAT_RANK.items()}


# =====================================================================
# Tactical branch definitions
# =====================================================================

# Each branch: (label, speed_factor, heading_delta_deg, base_probability)
_BRANCH_TEMPLATES = [
    ("continue_course",  1.0,   0.0,  0.40),
    ("accelerate",       1.5,   0.0,  0.10),
    ("decelerate",       0.3,   0.0,  0.10),
    ("turn_left",        0.9, -45.0,  0.10),
    ("turn_right",       0.9,  45.0,  0.10),
    ("stop",             0.0,   0.0,  0.08),
    ("reverse",         -0.5, 180.0,  0.07),
    ("evasive_maneuver", 1.2,  90.0,  0.05),
]


class ShortHorizonPredictor:
    """Produces multi-hypothesis forecasts over configurable time windows.

    All weights and parameters are constructor-configurable.
    The engine is stateless — every call is independent and deterministic
    given the same input snapshot.
    """

    def __init__(
        self,
        default_windows_s: Optional[List[float]] = None,
        max_hypotheses: int = 5,
        # Uncertainty growth parameters
        position_uncertainty_growth_rate: float = 2.0,   # metres per sqrt(second)
        heading_uncertainty_base_deg: float = 5.0,
        speed_uncertainty_base_mps: float = 1.0,
        # Confidence decay over horizon
        temporal_confidence_halflife_s: float = 300.0,
        # Volatility amplification factor
        volatility_amplification: float = 3.0,
        # Trend detection minimum history
        min_history_for_trend: int = 3,
    ) -> None:
        self.default_windows = default_windows_s or [30.0, 120.0, 600.0]
        self.max_hypotheses = max_hypotheses
        self.pos_unc_rate = position_uncertainty_growth_rate
        self.heading_unc_base = heading_uncertainty_base_deg
        self.speed_unc_base = speed_uncertainty_base_mps
        self.conf_halflife = temporal_confidence_halflife_s
        self.volatility_amp = volatility_amplification
        self.min_trend_history = min_history_for_trend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def forecast(
        self,
        entity: EntitySnapshot,
        windows_s: Optional[List[float]] = None,
        max_hypotheses: Optional[int] = None,
        doctrine_bias: Optional[str] = None,
    ) -> ForecastBundle:
        """Forecast one entity across all time windows.

        Parameters
        ----------
        entity : EntitySnapshot
            Current state + history of the entity to predict.
        windows_s : list of float, optional
            Override time horizons in seconds.
        max_hypotheses : int, optional
            Override max hypotheses per window.
        doctrine_bias : str, optional
            Bias toward "defensive" or "aggressive" interpretations.

        Returns
        -------
        ForecastBundle with all windows populated.
        """
        windows = windows_s or self.default_windows
        n_hyp = max_hypotheses or self.max_hypotheses

        # Analyze the entity
        trend = self._detect_trend(entity)
        vol = entity.volatility

        # Generate forecast for each window
        pred_windows: List[PredictionWindow] = []
        for w_s in sorted(windows):
            pw = self._forecast_window(entity, w_s, n_hyp, trend, vol, doctrine_bias)
            pred_windows.append(pw)

        bundle = ForecastBundle(
            request_id="",
            entity_id=entity.entity_id,
            entity_classification=entity.classification,
            windows=pred_windows,
            overall_trend=trend,
            volatility_score=vol,
            forecast_confidence=self._overall_confidence(entity, pred_windows),
        )
        return bundle

    def forecast_from_request(self, request: PredictionRequest) -> List[ForecastBundle]:
        """Forecast all entities in a request."""
        bundles: List[ForecastBundle] = []
        for entity in request.entities:
            bundle = self.forecast(
                entity,
                windows_s=request.windows_seconds,
                max_hypotheses=request.max_hypotheses,
                doctrine_bias=request.doctrine_bias,
            )
            bundle.request_id = request.request_id
            bundles.append(bundle)
        return bundles

    # ------------------------------------------------------------------
    # Per-window forecast
    # ------------------------------------------------------------------

    def _forecast_window(
        self,
        entity: EntitySnapshot,
        horizon_s: float,
        max_hyp: int,
        trend: ThreatPosture,
        volatility: float,
        doctrine_bias: Optional[str],
    ) -> PredictionWindow:
        """Generate all hypotheses for one time window."""
        hypotheses: List[PredictionHypothesis] = []

        for label, speed_factor, heading_delta, base_prob in _BRANCH_TEMPLATES:
            # Adjust probability based on trend and context
            prob = self._adjust_probability(
                base_prob, label, trend, volatility, entity, doctrine_bias,
            )
            if prob < 0.01:
                continue  # skip negligible branches

            # Project kinematic state
            state = self._extrapolate(entity, horizon_s, speed_factor, heading_delta)

            # Predict threat evolution
            state.predicted_threat_level = self._project_threat_level(
                entity, horizon_s, trend, label,
            )
            state.predicted_posture = self._label_to_posture(label, trend)
            state.movement_mode = self._label_to_movement(label)

            # Compute uncertainty
            uncertainty = self._compute_uncertainty(entity, horizon_s, volatility)

            # Build explanation
            explanation = self._build_explanation(
                entity, horizon_s, label, prob, trend, volatility,
            )

            hypotheses.append(PredictionHypothesis(
                label=label,
                probability=prob,
                predicted_state=state,
                uncertainty=uncertainty,
                explanation=explanation,
            ))

        # Normalize probabilities to sum to 1.0
        total_p = sum(h.probability for h in hypotheses)
        if total_p > 0:
            for h in hypotheses:
                h.probability /= total_p

        # Sort by probability descending, keep top N
        hypotheses.sort(key=lambda h: h.probability, reverse=True)
        hypotheses = hypotheses[:max_hyp]

        # Re-normalize after truncation
        total_p = sum(h.probability for h in hypotheses)
        if total_p > 0:
            for h in hypotheses:
                h.probability /= total_p

        # Build window
        dominant = hypotheses[0] if hypotheses else None
        agg_uncertainty = self._compute_uncertainty(entity, horizon_s, volatility)

        window = PredictionWindow(
            window_seconds=horizon_s,
            hypotheses=hypotheses,
            dominant_hypothesis_id=dominant.hypothesis_id if dominant else None,
            aggregate_uncertainty=agg_uncertainty,
        )
        return window

    # ------------------------------------------------------------------
    # Kinematic extrapolation
    # ------------------------------------------------------------------

    def _extrapolate(
        self,
        entity: EntitySnapshot,
        dt_s: float,
        speed_factor: float,
        heading_delta_deg: float,
    ) -> PredictedEntityState:
        """Linear kinematic projection with branch modifiers."""
        new_heading = (entity.heading_deg + heading_delta_deg) % 360.0
        new_speed = max(0.0, entity.speed_mps * speed_factor)

        heading_rad = math.radians(new_heading)
        vx = new_speed * math.cos(heading_rad)
        vy = new_speed * math.sin(heading_rad)
        vz = entity.velocity[2] * speed_factor if abs(speed_factor) > 0.01 else 0.0

        px = entity.position[0] + vx * dt_s
        py = entity.position[1] + vy * dt_s
        pz = entity.position[2] + vz * dt_s

        return PredictedEntityState(
            predicted_position=(round(px, 2), round(py, 2), round(pz, 2)),
            predicted_velocity=(round(vx, 2), round(vy, 2), round(vz, 2)),
            predicted_heading_deg=round(new_heading, 1),
            predicted_speed_mps=round(new_speed, 2),
            predicted_allegiance=entity.allegiance,
        )

    # ------------------------------------------------------------------
    # Uncertainty computation
    # ------------------------------------------------------------------

    def _compute_uncertainty(
        self,
        entity: EntitySnapshot,
        horizon_s: float,
        volatility: float,
    ) -> UncertaintyEstimate:
        """Compute uncertainty that grows with time horizon and volatility.

        Spatial uncertainty grows as rate × sqrt(t) × (1 + volatility × amplification).
        Temporal confidence decays exponentially with half-life.
        """
        vol_factor = 1.0 + volatility * self.volatility_amp
        sqrt_t = math.sqrt(max(0.1, horizon_s))

        spatial = self.pos_unc_rate * sqrt_t * vol_factor
        heading_std = self.heading_unc_base * sqrt_t * vol_factor * 0.5
        speed_std = self.speed_unc_base * sqrt_t * vol_factor * 0.3

        # Temporal confidence: 2^(-t / halflife)
        temporal_conf = math.pow(2.0, -horizon_s / self.conf_halflife)

        # Threat level entropy: higher if entity is volatile or near a transition
        threat_entropy = min(2.0, 0.3 + volatility * 1.5 + (1.0 - entity.confidence) * 0.5)

        return UncertaintyEstimate(
            spatial_radius_m=round(spatial, 2),
            heading_std_deg=round(heading_std, 1),
            speed_std_mps=round(speed_std, 2),
            threat_level_entropy=round(threat_entropy, 3),
            temporal_confidence=round(temporal_conf, 4),
        )

    # ------------------------------------------------------------------
    # Trend detection from history
    # ------------------------------------------------------------------

    def _detect_trend(self, entity: EntitySnapshot) -> ThreatPosture:
        """Detect behavioral trend from recent state history."""
        if len(entity.history) < self.min_trend_history:
            return ThreatPosture.UNKNOWN

        recent = entity.history[-min(10, len(entity.history)):]

        # Check threat level progression
        threat_ranks = [_THREAT_RANK.get(h.threat_level, 0) for h in recent]
        non_zero = [r for r in threat_ranks if r > 0]

        if len(non_zero) >= 3:
            deltas = [non_zero[i] - non_zero[i - 1] for i in range(1, len(non_zero))]
            avg_delta = sum(deltas) / len(deltas) if deltas else 0
            if avg_delta > 0.3:
                return ThreatPosture.ESCALATING
            if avg_delta < -0.3:
                return ThreatPosture.DE_ESCALATING

        # Check speed trend
        speeds = [h.speed_mps for h in recent]
        if len(speeds) >= 3:
            speed_deltas = [speeds[i] - speeds[i - 1] for i in range(1, len(speeds))]
            avg_speed_delta = sum(speed_deltas) / len(speed_deltas)
            if avg_speed_delta < -1.0 and speeds[-1] < 1.0:
                return ThreatPosture.WITHDRAWING

        # Check heading variance for maneuvering
        headings = [h.heading_deg for h in recent]
        if _variance(headings) > 400:  # >20 deg std
            return ThreatPosture.MANEUVERING

        return ThreatPosture.STABLE

    # ------------------------------------------------------------------
    # Probability adjustment
    # ------------------------------------------------------------------

    def _adjust_probability(
        self,
        base_prob: float,
        label: str,
        trend: ThreatPosture,
        volatility: float,
        entity: EntitySnapshot,
        doctrine_bias: Optional[str],
    ) -> float:
        """Adjust branch probability based on context.

        Trend modifiers:
          - ESCALATING: boost accelerate/continue, suppress stop/reverse
          - DE_ESCALATING: boost decelerate/stop, suppress accelerate
          - WITHDRAWING: boost reverse, suppress continue
          - MANEUVERING: boost turns/evasive, suppress continue
          - STABLE: boost continue, suppress evasive

        Volatility: boost erratic branches, suppress stable ones.
        Doctrine: defensive boosts cautious predictions.
        """
        p = base_prob

        # Trend adjustments
        if trend == ThreatPosture.ESCALATING:
            if label in ("continue_course", "accelerate"):
                p *= 1.5
            elif label in ("stop", "reverse", "decelerate"):
                p *= 0.3
        elif trend == ThreatPosture.DE_ESCALATING:
            if label in ("decelerate", "stop"):
                p *= 1.8
            elif label in ("accelerate", "evasive_maneuver"):
                p *= 0.3
        elif trend == ThreatPosture.WITHDRAWING:
            if label == "reverse":
                p *= 3.0
            elif label == "continue_course":
                p *= 0.5
        elif trend == ThreatPosture.MANEUVERING:
            if label in ("turn_left", "turn_right", "evasive_maneuver"):
                p *= 2.0
            elif label == "continue_course":
                p *= 0.5
        elif trend == ThreatPosture.STABLE:
            if label == "continue_course":
                p *= 1.6
            elif label in ("evasive_maneuver", "reverse"):
                p *= 0.3

        # Volatility: erratic entities are less predictable
        if volatility > 0.5:
            if label == "continue_course":
                p *= (1.0 - volatility * 0.5)
            elif label in ("evasive_maneuver", "turn_left", "turn_right"):
                p *= (1.0 + volatility)

        # Stopped entity: strongly boost "stop", suppress movement branches
        if not entity.is_moving:
            if label == "stop":
                p *= 5.0
            elif label in ("continue_course", "accelerate", "turn_left", "turn_right"):
                p *= 0.2
            elif label == "reverse":
                p *= 0.1

        # Doctrine bias
        if doctrine_bias == "defensive":
            if label in ("stop", "reverse", "decelerate"):
                p *= 1.3
        elif doctrine_bias == "aggressive":
            if label in ("accelerate", "continue_course"):
                p *= 1.3

        return max(0.0, p)

    # ------------------------------------------------------------------
    # Threat level projection
    # ------------------------------------------------------------------

    def _project_threat_level(
        self,
        entity: EntitySnapshot,
        horizon_s: float,
        trend: ThreatPosture,
        branch_label: str,
    ) -> str:
        """Project the threat level forward in time."""
        current_rank = _THREAT_RANK.get(entity.threat_level, 0)
        if current_rank == 0:
            return entity.threat_level

        delta = 0
        if trend == ThreatPosture.ESCALATING:
            delta = 1 if horizon_s > 60 else 0
        elif trend == ThreatPosture.DE_ESCALATING:
            delta = -1 if horizon_s > 60 else 0

        if branch_label in ("accelerate", "evasive_maneuver"):
            delta = max(delta, 0) + (1 if horizon_s > 120 else 0)
        elif branch_label in ("stop", "reverse"):
            delta = min(delta, 0) - (1 if horizon_s > 60 else 0)

        projected_rank = max(1, min(5, current_rank + delta))
        return _RANK_THREAT.get(projected_rank, entity.threat_level)

    # ------------------------------------------------------------------
    # Label → enum mappings
    # ------------------------------------------------------------------

    @staticmethod
    def _label_to_posture(label: str, trend: ThreatPosture) -> ThreatPosture:
        mapping = {
            "continue_course": trend if trend != ThreatPosture.UNKNOWN else ThreatPosture.STABLE,
            "accelerate": ThreatPosture.ESCALATING,
            "decelerate": ThreatPosture.DE_ESCALATING,
            "stop": ThreatPosture.DE_ESCALATING,
            "turn_left": ThreatPosture.MANEUVERING,
            "turn_right": ThreatPosture.MANEUVERING,
            "reverse": ThreatPosture.WITHDRAWING,
            "evasive_maneuver": ThreatPosture.MANEUVERING,
        }
        return mapping.get(label, ThreatPosture.UNKNOWN)

    @staticmethod
    def _label_to_movement(label: str) -> MovementMode:
        mapping = {
            "continue_course": MovementMode.CONTINUE_COURSE,
            "accelerate": MovementMode.ACCELERATING,
            "decelerate": MovementMode.DECELERATING,
            "stop": MovementMode.STOPPED,
            "turn_left": MovementMode.TURNING,
            "turn_right": MovementMode.TURNING,
            "reverse": MovementMode.REVERSING,
            "evasive_maneuver": MovementMode.ERRATIC,
        }
        return mapping.get(label, MovementMode.UNKNOWN)

    # ------------------------------------------------------------------
    # Explanation generation
    # ------------------------------------------------------------------

    def _build_explanation(
        self,
        entity: EntitySnapshot,
        horizon_s: float,
        label: str,
        probability: float,
        trend: ThreatPosture,
        volatility: float,
    ) -> ExplanationBlock:
        """Build human-readable explanation for a hypothesis."""
        factors: List[str] = []
        observations: List[str] = []
        uncertainty_notes: List[str] = []

        # Primary factors
        factors.append(f"Branch '{label}' from kinematic extrapolation over {horizon_s:.0f}s")
        if trend != ThreatPosture.UNKNOWN:
            factors.append(f"Behavioral trend: {trend.value}")
        if entity.is_moving:
            factors.append(f"Entity moving at {entity.speed_mps:.1f} m/s, heading {entity.heading_deg:.0f}°")
        else:
            factors.append("Entity is stationary")

        # Supporting observations
        if entity.history_depth >= 3:
            observations.append(f"Based on {entity.history_depth} historical state observations")
        if entity.threat_level != "unknown":
            observations.append(f"Current threat assessment: {entity.threat_level}")
        if entity.confidence > 0.7:
            observations.append(f"High-confidence entity (conf={entity.confidence:.2f})")
        elif entity.confidence < 0.4:
            observations.append(f"Low-confidence entity (conf={entity.confidence:.2f})")

        # Uncertainty notes
        if horizon_s > 300:
            uncertainty_notes.append("Long forecast horizon increases positional uncertainty significantly")
        if volatility > 0.5:
            uncertainty_notes.append(f"Entity is volatile (score={volatility:.2f}), predictions less reliable")
        if entity.history_depth < 3:
            uncertainty_notes.append("Insufficient history for reliable trend detection")
        if entity.confidence < 0.5:
            uncertainty_notes.append("Low entity confidence degrades forecast reliability")

        methodology = (
            "Recency-weighted kinematic extrapolation with behavioral trend modulation "
            "and probabilistic branching. Uncertainty scales as sqrt(t) × volatility."
        )

        return ExplanationBlock(
            primary_factors=factors,
            supporting_observations=observations,
            uncertainty_notes=uncertainty_notes,
            methodology=methodology,
        )

    # ------------------------------------------------------------------
    # Overall confidence
    # ------------------------------------------------------------------

    def _overall_confidence(
        self,
        entity: EntitySnapshot,
        windows: List[PredictionWindow],
    ) -> float:
        """Compute overall forecast confidence across all windows."""
        if not windows:
            return 0.0

        # Average temporal confidence across windows
        confidences = []
        for w in windows:
            if w.aggregate_uncertainty:
                confidences.append(w.aggregate_uncertainty.temporal_confidence)

        avg_temporal = sum(confidences) / len(confidences) if confidences else 0.5

        # Factor in entity confidence and history depth
        history_factor = min(1.0, entity.history_depth / 10.0)
        entity_conf_factor = entity.confidence

        return round(
            avg_temporal * 0.4 + entity_conf_factor * 0.35 + history_factor * 0.25,
            3,
        )
