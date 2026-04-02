"""Live Simulation Mirror — parallel predicted-vs-observed state comparison.

Runs predicted state beside real-world fused state and measures:
  - Position error (Euclidean distance)
  - Classification / threat-level drift
  - Confidence calibration error
  - Missing entity detection
  - False persistence / false disappearance

Produces:
  - MirrorComparison for each entity×timestep
  - DriftSignal when predictions consistently diverge
  - ValidationMetric accumulated over time
  - MirrorFeedback for tuning the prediction engine

Usage::

    mirror = LiveSimulationMirror()
    mirror.record_prediction(predicted_frame)
    # ... time passes, observation arrives ...
    mirror.record_observation(observed_frame)
    comparisons = mirror.compare_pending()
    drift_signals = mirror.detect_drift("ent-001")
    metrics = mirror.get_validation_metrics()
    feedback = mirror.generate_feedback()
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .mirror_models import (
    ComparisonOutcome,
    DriftSeverity,
    DriftSignal,
    MirrorComparison,
    MirrorFeedback,
    MirrorFrame,
    ObservedStateFrame,
    PredictedStateFrame,
    ValidationMetric,
)


class LiveSimulationMirror:
    """Parallel state tracker and prediction validator.

    Thread-safe is NOT required for this chunk — the mirror is designed
    to be called sequentially from the main prediction/fusion loop.
    """

    def __init__(
        self,
        # Comparison thresholds
        position_accurate_m: float = 50.0,  # < this = accurate position
        position_partial_m: float = 200.0,  # < this = partial match
        heading_accurate_deg: float = 15.0,
        speed_accurate_mps: float = 5.0,
        # Drift detection
        drift_window_size: int = 5,  # comparisons to average
        drift_position_threshold_m: float = 150.0,  # mean error to trigger drift
        drift_calibration_threshold: float = 0.3,
        # History limits
        max_frames_per_entity: int = 200,
        max_feedback_items: int = 500,
    ) -> None:
        self.pos_accurate = position_accurate_m
        self.pos_partial = position_partial_m
        self.heading_accurate = heading_accurate_deg
        self.speed_accurate = speed_accurate_mps
        self.drift_window = drift_window_size
        self.drift_pos_thresh = drift_position_threshold_m
        self.drift_cal_thresh = drift_calibration_threshold
        self.max_frames = max_frames_per_entity
        self.max_feedback = max_feedback_items

        # Storage: entity_id → list of MirrorFrames
        self._frames: Dict[str, List[MirrorFrame]] = defaultdict(list)

        # Pending predicted frames awaiting observations
        self._pending_predicted: Dict[str, List[PredictedStateFrame]] = defaultdict(list)

        # Accumulated comparisons for metrics
        self._all_comparisons: List[MirrorComparison] = []
        self._drift_signals: List[DriftSignal] = []
        self._feedback: List[MirrorFeedback] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_prediction(self, predicted: PredictedStateFrame) -> str:
        """Record a prediction to be compared against future observations."""
        self._pending_predicted[predicted.entity_id].append(predicted)
        # Trim
        if len(self._pending_predicted[predicted.entity_id]) > self.max_frames:
            self._pending_predicted[predicted.entity_id] = self._pending_predicted[predicted.entity_id][-self.max_frames :]
        return predicted.frame_id

    def record_observation(self, observed: ObservedStateFrame) -> str:
        """Record an observation (what actually happened)."""
        eid = observed.entity_id
        # Try to match against pending predictions
        matched = self._match_prediction(eid, observed.observation_timestamp)
        if matched:
            frame = MirrorFrame(
                entity_id=eid,
                horizon_s=matched.horizon_s,
                predicted=matched,
                observed=observed,
            )
            comparison = self._compare(matched, observed)
            frame.comparison = comparison
            self._frames[eid].append(frame)
            self._all_comparisons.append(comparison)

            # Trim
            if len(self._frames[eid]) > self.max_frames:
                self._frames[eid] = self._frames[eid][-self.max_frames :]
        else:
            # Unexpected entity — no prediction existed
            frame = MirrorFrame(
                entity_id=eid,
                observed=observed,
            )
            comparison = MirrorComparison(
                entity_id=eid,
                outcome=ComparisonOutcome.UNEXPECTED_ENTITY,
                entity_was_present=observed.entity_present,
                notes=["No prediction existed for this entity at this time"],
            )
            frame.comparison = comparison
            self._frames[eid].append(frame)
            self._all_comparisons.append(comparison)

        return observed.frame_id

    def record_entity_disappeared(self, entity_id: str) -> None:
        """Record that a predicted entity was not observed (false persistence)."""
        pending = self._pending_predicted.get(entity_id, [])
        for pred in pending:
            comparison = MirrorComparison(
                entity_id=entity_id,
                horizon_s=pred.horizon_s,
                outcome=ComparisonOutcome.FALSE_PERSISTENCE,
                predicted_confidence=pred.predicted_confidence,
                actual_outcome_probability=0.0,
                calibration_error=pred.predicted_confidence,
                entity_was_present=False,
                notes=[f"Entity {entity_id} predicted but not observed (false persistence)"],
            )
            frame = MirrorFrame(
                entity_id=entity_id,
                horizon_s=pred.horizon_s,
                predicted=pred,
                comparison=comparison,
            )
            self._frames[entity_id].append(frame)
            self._all_comparisons.append(comparison)
        self._pending_predicted.pop(entity_id, None)

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def _compare(self, predicted: PredictedStateFrame, observed: ObservedStateFrame) -> MirrorComparison:
        """Compute comparison metrics between predicted and observed state."""
        notes: List[str] = []

        # Position error
        pos_err = _euclidean_3d(predicted.predicted_position, observed.observed_position)

        # Heading error (angular, 0-180)
        heading_err = abs(predicted.predicted_heading_deg - observed.observed_heading_deg)
        heading_err = min(heading_err, 360.0 - heading_err)

        # Speed error
        speed_err = abs(predicted.predicted_speed_mps - observed.observed_speed_mps)

        # Threat level match
        threat_match = predicted.predicted_threat_level.lower() == observed.observed_threat_level.lower()

        # Label match — infer "actual label" from observed movement
        actual_label = self._infer_actual_label(observed)
        label_match = predicted.predicted_label == actual_label

        # Determine outcome
        if not observed.entity_present:
            outcome = ComparisonOutcome.ENTITY_MISSING
            notes.append("Entity was not observed at target time")
        elif pos_err <= self.pos_accurate and threat_match:
            outcome = ComparisonOutcome.ACCURATE
        elif pos_err <= self.pos_partial:
            outcome = ComparisonOutcome.PARTIAL_MATCH
            if not threat_match:
                notes.append(
                    "Threat level mismatch: "
                    f"predicted={predicted.predicted_threat_level}, "
                    f"observed={observed.observed_threat_level}"
                )
        else:
            outcome = ComparisonOutcome.INACCURATE
            notes.append(f"Position error {pos_err:.1f}m exceeds threshold {self.pos_partial:.0f}m")

        # Calibration error
        actual_prob = 1.0 if outcome in (ComparisonOutcome.ACCURATE, ComparisonOutcome.PARTIAL_MATCH) else 0.0
        cal_error = abs(predicted.predicted_confidence - actual_prob)

        return MirrorComparison(
            entity_id=predicted.entity_id,
            horizon_s=predicted.horizon_s,
            outcome=outcome,
            position_error_m=pos_err,
            heading_error_deg=heading_err,
            speed_error_mps=speed_err,
            threat_level_match=threat_match,
            label_match=label_match,
            predicted_confidence=predicted.predicted_confidence,
            actual_outcome_probability=actual_prob,
            calibration_error=cal_error,
            entity_was_present=observed.entity_present,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def detect_drift(self, entity_id: str = "") -> List[DriftSignal]:
        """Detect prediction drift for one or all entities."""
        signals: List[DriftSignal] = []
        entities = [entity_id] if entity_id else list(self._frames.keys())

        for eid in entities:
            frames = self._frames.get(eid, [])
            recent = [f for f in frames[-self.drift_window :] if f.comparison]
            if len(recent) < 2:
                continue

            comparisons = [f.comparison for f in recent if f.comparison]

            # Position drift
            pos_errors = [c.position_error_m for c in comparisons]
            mean_pos_err = sum(pos_errors) / len(pos_errors)
            if mean_pos_err > self.drift_pos_thresh:
                severity = self._classify_drift_severity(mean_pos_err, self.drift_pos_thresh)
                sig = DriftSignal(
                    entity_id=eid,
                    severity=severity,
                    drift_type="position",
                    metric_value=mean_pos_err,
                    threshold=self.drift_pos_thresh,
                    window_comparisons=len(comparisons),
                    explanation=(
                        f"Mean position error {mean_pos_err:.1f}m over "
                        f"{len(comparisons)} comparisons exceeds "
                        f"{self.drift_pos_thresh:.0f}m threshold"
                    ),
                )
                signals.append(sig)
                self._drift_signals.append(sig)

            # Calibration drift
            cal_errors = [c.calibration_error for c in comparisons]
            mean_cal_err = sum(cal_errors) / len(cal_errors)
            if mean_cal_err > self.drift_cal_thresh:
                severity = self._classify_drift_severity(mean_cal_err / self.drift_cal_thresh, 1.0)
                sig = DriftSignal(
                    entity_id=eid,
                    severity=severity,
                    drift_type="confidence",
                    metric_value=mean_cal_err,
                    threshold=self.drift_cal_thresh,
                    window_comparisons=len(comparisons),
                    explanation=(
                        f"Mean calibration error {mean_cal_err:.3f} over "
                        f"{len(comparisons)} comparisons exceeds "
                        f"{self.drift_cal_thresh} threshold"
                    ),
                )
                signals.append(sig)
                self._drift_signals.append(sig)

            # Classification drift
            threat_mismatches = sum(1 for c in comparisons if not c.threat_level_match)
            if threat_mismatches > len(comparisons) * 0.5 and len(comparisons) >= 3:
                sig = DriftSignal(
                    entity_id=eid,
                    severity=DriftSeverity.MODERATE,
                    drift_type="classification",
                    metric_value=threat_mismatches / len(comparisons),
                    threshold=0.5,
                    window_comparisons=len(comparisons),
                    explanation=f"{threat_mismatches}/{len(comparisons)} threat level mismatches",
                )
                signals.append(sig)
                self._drift_signals.append(sig)

        return signals

    # ------------------------------------------------------------------
    # Validation metrics
    # ------------------------------------------------------------------

    def get_validation_metrics(self, window_label: str = "all") -> ValidationMetric:
        """Compute accumulated validation metrics."""
        comps = self._all_comparisons
        if not comps:
            return ValidationMetric(window_label=window_label)

        total = len(comps)
        correct_labels = sum(1 for c in comps if c.label_match)
        present = sum(1 for c in comps if c.entity_was_present)
        pos_errors = [c.position_error_m for c in comps if c.entity_was_present]

        label_precision = correct_labels / total if total > 0 else 0.0
        detection_recall = present / total if total > 0 else 0.0
        mean_pos_err = sum(pos_errors) / len(pos_errors) if pos_errors else 0.0
        max_pos_err = max(pos_errors) if pos_errors else 0.0
        cal_errors = [c.calibration_error for c in comps]
        mean_cal = sum(cal_errors) / len(cal_errors) if cal_errors else 0.0

        return ValidationMetric(
            window_label=window_label,
            total_comparisons=total,
            correct_label_predictions=correct_labels,
            label_precision=label_precision,
            entities_observed=present,
            entities_predicted=total,
            detection_recall=detection_recall,
            mean_position_error_m=mean_pos_err,
            max_position_error_m=max_pos_err,
            mean_calibration_error=mean_cal,
            drift_signals_generated=len(self._drift_signals),
        )

    # ------------------------------------------------------------------
    # Feedback generation
    # ------------------------------------------------------------------

    def generate_feedback(self, last_n: int = 50) -> List[MirrorFeedback]:
        """Generate machine-readable feedback for prediction engine tuning."""
        feedback: List[MirrorFeedback] = []

        for comp in self._all_comparisons[-last_n:]:
            adjustments: Dict[str, Any] = {}

            if comp.position_error_m > self.pos_partial:
                adjustments["increase_position_uncertainty"] = True
                adjustments["position_error_observed"] = comp.position_error_m

            if comp.calibration_error > 0.3:
                adjustments["recalibrate_confidence"] = True
                adjustments["calibration_error_observed"] = comp.calibration_error

            if not comp.threat_level_match:
                adjustments["review_threat_classification"] = True

            actual_label = "unknown"
            for frame_list in self._frames.values():
                for frame in frame_list:
                    if frame.comparison and frame.comparison.comparison_id == comp.comparison_id:
                        if frame.observed:
                            actual_label = self._infer_actual_label(frame.observed)
                        break

            fb = MirrorFeedback(
                entity_id=comp.entity_id,
                horizon_s=comp.horizon_s,
                predicted_label=comp.notes[0] if comp.notes else "",
                actual_outcome=comp.outcome.value,
                position_error_m=comp.position_error_m,
                calibration_error=comp.calibration_error,
                recommended_adjustments=adjustments,
            )
            feedback.append(fb)

        self._feedback.extend(feedback)
        if len(self._feedback) > self.max_feedback:
            self._feedback = self._feedback[-self.max_feedback :]

        return feedback

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_frames(self, entity_id: str, last_n: int = 20) -> List[Dict[str, Any]]:
        return [f.to_dict() for f in self._frames.get(entity_id, [])[-last_n:]]

    def get_drift_signals(self, last_n: int = 20) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._drift_signals[-last_n:]]

    def get_entity_ids(self) -> List[str]:
        return list(self._frames.keys())

    def stats(self) -> Dict[str, Any]:
        return {
            "entities_tracked": len(self._frames),
            "total_frames": sum(len(v) for v in self._frames.values()),
            "pending_predictions": sum(len(v) for v in self._pending_predicted.values()),
            "total_comparisons": len(self._all_comparisons),
            "drift_signals": len(self._drift_signals),
            "feedback_items": len(self._feedback),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _match_prediction(self, entity_id: str, obs_time: datetime) -> Optional[PredictedStateFrame]:
        """Find the best matching prediction for an observation timestamp."""
        pending = self._pending_predicted.get(entity_id, [])
        if not pending:
            return None

        best: Optional[PredictedStateFrame] = None
        best_gap = float("inf")
        best_idx = -1

        for idx, pred in enumerate(pending):
            gap = abs((obs_time - pred.target_timestamp).total_seconds())
            if gap < best_gap:
                best_gap = gap
                best = pred
                best_idx = idx

        # Remove matched prediction
        if best is not None and best_idx >= 0:
            pending.pop(best_idx)

        return best

    @staticmethod
    def _infer_actual_label(observed: ObservedStateFrame) -> str:
        """Infer a behavior label from observed state."""
        if observed.observed_speed_mps < 0.5:
            return "stop"
        if observed.observed_speed_mps > 30.0:
            return "accelerate"
        return "continue_course"

    @staticmethod
    def _classify_drift_severity(value: float, threshold: float) -> DriftSeverity:
        ratio = value / max(0.001, threshold)
        if ratio < 1.2:
            return DriftSeverity.MINOR
        if ratio < 2.0:
            return DriftSeverity.MODERATE
        if ratio < 3.5:
            return DriftSeverity.MAJOR
        return DriftSeverity.CRITICAL


# =====================================================================
# Helpers
# =====================================================================


def _euclidean_3d(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)
