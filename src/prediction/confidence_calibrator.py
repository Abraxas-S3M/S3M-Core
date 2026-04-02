"""Multi-factor confidence calibration for prediction outputs.

Raw prediction scores are mechanistic - they come from branch probability
times trend modulation. Calibrated confidence accounts for the epistemic
quality of the prediction:

  1. Source reliability: are the input observations trustworthy?
  2. Data richness: how much history do we have?
  3. Observation agreement: do recent observations agree or conflict?
  4. Pattern match strength: does a known motif support this prediction?
  5. Horizon penalty: longer horizons are inherently less certain
  6. Historical accuracy: how well have past predictions performed?

The calibrator produces a CalibratedConfidence object that separates
raw_score from calibrated_score and includes a rationale summary.

Usage::

    calibrator = ConfidenceCalibrator()
    calibrated = calibrator.calibrate(
        raw_score=0.65,
        entity=snapshot,
        horizon_s=120.0,
        pattern_match_score=0.8,
    )
    # calibrated.calibrated_score may differ from raw 0.65
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List


# =====================================================================
# Calibrated confidence output
# =====================================================================


@dataclass
class CalibratedConfidence:
    """Calibrated prediction confidence with factor decomposition.

    Separates the mechanistic raw_score from the epistemically
    calibrated_score and provides a human-readable rationale.
    """

    raw_score: float = 0.0
    calibrated_score: float = 0.0

    # Per-factor contributions (0-1 each)
    source_reliability_factor: float = 0.5
    data_richness_factor: float = 0.5
    observation_agreement_factor: float = 1.0
    pattern_match_factor: float = 0.0
    horizon_penalty_factor: float = 1.0
    historical_accuracy_factor: float = 0.5

    # Uncertainty band: [low, high] around calibrated score
    confidence_low: float = 0.0
    confidence_high: float = 1.0

    # Human-readable rationale
    rationale: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_score": round(self.raw_score, 4),
            "calibrated_score": round(self.calibrated_score, 4),
            "confidence_band": [round(self.confidence_low, 4), round(self.confidence_high, 4)],
            "factors": {
                "source_reliability": round(self.source_reliability_factor, 3),
                "data_richness": round(self.data_richness_factor, 3),
                "observation_agreement": round(self.observation_agreement_factor, 3),
                "pattern_match": round(self.pattern_match_factor, 3),
                "horizon_penalty": round(self.horizon_penalty_factor, 3),
                "historical_accuracy": round(self.historical_accuracy_factor, 3),
            },
            "rationale": list(self.rationale),
        }


# =====================================================================
# Accuracy tracker (lightweight rolling stats)
# =====================================================================


@dataclass
class _AccuracyRecord:
    predicted_label: str
    actual_label: str
    horizon_s: float
    correct: bool


class ConfidenceCalibrator:
    """Calibrates prediction confidence using multi-factor analysis.

    All factor weights are configurable. The calibrator maintains an
    optional accuracy history for self-calibration over time.
    """

    def __init__(
        self,
        # Factor weights (how much each factor influences calibration)
        w_source_reliability: float = 0.15,
        w_data_richness: float = 0.20,
        w_observation_agreement: float = 0.15,
        w_pattern_match: float = 0.20,
        w_horizon_penalty: float = 0.20,
        w_historical_accuracy: float = 0.10,
        # Horizon penalty parameters
        horizon_halflife_s: float = 300.0,
        # Data richness thresholds
        rich_history_threshold: int = 8,
        sparse_history_threshold: int = 2,
        # Disagreement detection threshold
        disagreement_heading_var: float = 400.0,
        disagreement_speed_var: float = 100.0,
        # Uncertainty band width
        base_band_width: float = 0.15,
        # Accuracy tracker capacity
        accuracy_history_limit: int = 500,
    ) -> None:
        self.weights = {
            "source_reliability": w_source_reliability,
            "data_richness": w_data_richness,
            "observation_agreement": w_observation_agreement,
            "pattern_match": w_pattern_match,
            "horizon_penalty": w_horizon_penalty,
            "historical_accuracy": w_historical_accuracy,
        }
        # Normalize weights
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

        self.horizon_halflife = horizon_halflife_s
        self.rich_threshold = rich_history_threshold
        self.sparse_threshold = sparse_history_threshold
        self.disagree_heading_var = disagreement_heading_var
        self.disagree_speed_var = disagreement_speed_var
        self.base_band = base_band_width
        self._accuracy_history: List[_AccuracyRecord] = []
        self._accuracy_limit = accuracy_history_limit

    # ------------------------------------------------------------------
    # Main calibration
    # ------------------------------------------------------------------

    def calibrate(
        self,
        raw_score: float,
        entity_confidence: float = 0.5,
        history_depth: int = 0,
        heading_variance: float = 0.0,
        speed_variance: float = 0.0,
        threat_level_changes: int = 0,
        pattern_match_score: float = 0.0,
        horizon_s: float = 30.0,
        source_reliability: float = 0.5,
    ) -> CalibratedConfidence:
        """Calibrate a raw prediction score.

        Parameters
        ----------
        raw_score : float
            Mechanistic prediction probability (0-1).
        entity_confidence : float
            Confidence in the entity's current state (from fusion).
        history_depth : int
            Number of historical observations available.
        heading_variance : float
            Variance in heading across recent history.
        speed_variance : float
            Variance in speed across recent history.
        threat_level_changes : int
            Number of threat-level changes in history.
        pattern_match_score : float
            Best motif match score from PatternMemory (0-1).
        horizon_s : float
            Forecast horizon in seconds.
        source_reliability : float
            Average source reliability of contributing observations.

        Returns
        -------
        CalibratedConfidence with decomposed factors and rationale.
        """
        rationale: List[str] = []

        # Factor 1: Source reliability
        f_source = min(1.0, source_reliability)
        if f_source < 0.4:
            rationale.append(f"Low source reliability ({f_source:.2f}) reduces confidence")
        elif f_source > 0.8:
            rationale.append(f"High source reliability ({f_source:.2f}) supports confidence")

        # Factor 2: Data richness
        if history_depth >= self.rich_threshold:
            f_richness = 1.0
            rationale.append(f"Rich history ({history_depth} points) supports forecast")
        elif history_depth <= self.sparse_threshold:
            f_richness = max(0.2, history_depth / max(1, self.rich_threshold))
            rationale.append(f"Sparse data ({history_depth} points) limits forecast reliability")
        else:
            f_richness = history_depth / self.rich_threshold

        # Factor 3: Observation agreement
        has_heading_disagree = heading_variance > self.disagree_heading_var
        has_speed_disagree = speed_variance > self.disagree_speed_var
        has_threat_conflict = threat_level_changes > 2

        disagreement_count = sum([has_heading_disagree, has_speed_disagree, has_threat_conflict])
        if disagreement_count == 0:
            f_agreement = 1.0
        elif disagreement_count == 1:
            f_agreement = 0.7
            rationale.append("Moderate observation disagreement detected")
        else:
            f_agreement = max(0.3, 1.0 - 0.25 * disagreement_count)
            rationale.append(f"Significant disagreement across {disagreement_count} dimensions lowers confidence")

        # Factor 4: Pattern match strength
        if pattern_match_score > 0.7:
            f_pattern = min(1.0, 0.5 + pattern_match_score * 0.5)
            rationale.append(f"Strong pattern match ({pattern_match_score:.2f}) boosts confidence")
        elif pattern_match_score > 0.3:
            f_pattern = 0.3 + pattern_match_score * 0.4
        elif pattern_match_score > 0:
            f_pattern = pattern_match_score
            rationale.append(f"Weak pattern match ({pattern_match_score:.2f})")
        else:
            f_pattern = 0.3
            rationale.append("No pattern match available")

        # Factor 5: Horizon penalty
        f_horizon = math.pow(2.0, -horizon_s / self.horizon_halflife)
        if horizon_s > 300:
            rationale.append(f"Long horizon ({horizon_s:.0f}s) significantly penalises confidence")
        elif horizon_s > 60:
            rationale.append(f"Medium horizon ({horizon_s:.0f}s) moderately penalises confidence")

        # Factor 6: Historical accuracy
        f_accuracy = self._compute_historical_accuracy()
        if self._accuracy_history:
            rationale.append(f"Historical accuracy factor: {f_accuracy:.2f}")
        else:
            rationale.append("No historical accuracy data; using neutral prior")

        # entity_confidence is included for API compatibility with upstream callers.
        _ = entity_confidence

        # Combine factors via weighted product
        calibrated = raw_score * (
            (f_source**self.weights["source_reliability"])
            * (f_richness**self.weights["data_richness"])
            * (f_agreement**self.weights["observation_agreement"])
            * (f_pattern**self.weights["pattern_match"])
            * (f_horizon**self.weights["horizon_penalty"])
            * (f_accuracy**self.weights["historical_accuracy"])
        )
        calibrated = max(0.01, min(0.99, calibrated))

        # Uncertainty band
        band_width = self.base_band * (1.0 + (1.0 - f_agreement) + (1.0 - f_richness) * 0.5)
        conf_low = max(0.0, calibrated - band_width)
        conf_high = min(1.0, calibrated + band_width)

        return CalibratedConfidence(
            raw_score=raw_score,
            calibrated_score=calibrated,
            source_reliability_factor=f_source,
            data_richness_factor=f_richness,
            observation_agreement_factor=f_agreement,
            pattern_match_factor=f_pattern,
            horizon_penalty_factor=f_horizon,
            historical_accuracy_factor=f_accuracy,
            confidence_low=conf_low,
            confidence_high=conf_high,
            rationale=rationale,
        )

    # ------------------------------------------------------------------
    # Historical accuracy tracking
    # ------------------------------------------------------------------

    def record_outcome(self, predicted_label: str, actual_label: str, horizon_s: float) -> None:
        """Record a prediction outcome for self-calibration."""
        self._accuracy_history.append(
            _AccuracyRecord(
                predicted_label=predicted_label,
                actual_label=actual_label,
                horizon_s=horizon_s,
                correct=(predicted_label == actual_label),
            )
        )
        if len(self._accuracy_history) > self._accuracy_limit:
            self._accuracy_history = self._accuracy_history[-self._accuracy_limit :]

    def _compute_historical_accuracy(self) -> float:
        """Compute rolling accuracy from recorded outcomes."""
        if not self._accuracy_history:
            return 0.5  # neutral prior
        correct = sum(1 for r in self._accuracy_history if r.correct)
        return correct / len(self._accuracy_history)

    def get_accuracy_stats(self) -> Dict[str, Any]:
        if not self._accuracy_history:
            return {"samples": 0, "accuracy": 0.5, "note": "no outcomes recorded"}
        correct = sum(1 for r in self._accuracy_history if r.correct)
        return {
            "samples": len(self._accuracy_history),
            "accuracy": round(correct / len(self._accuracy_history), 4),
            "recent_10": round(
                sum(1 for r in self._accuracy_history[-10:] if r.correct) / min(10, len(self._accuracy_history)), 4
            ),
        }
