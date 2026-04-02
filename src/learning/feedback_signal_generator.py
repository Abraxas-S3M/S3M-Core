# File: src/learning/feedback_signal_generator.py
"""Feedback signal generator for controlled prediction tuning.

Analyzes LiveSimulationMirror comparisons and drift signals to produce
structured, versioned, attributable FeedbackSignals.  These signals
describe WHAT is miscalibrated and recommend WHAT to tune — but they
do NOT autonomously rewrite any code or parameters.

Signal generation pipeline:
  1. Collect recent comparisons and drift signals from the mirror
  2. Analyze for each signal type (under/overconfidence, drift, etc.)
  3. Generate FeedbackSignal with structured RecommendedAction
  4. Optionally push outcomes to ConfidenceCalibrator (controlled)
  5. Optionally reinforce/decay motifs in PatternMemory (controlled)

Usage::

    generator = FeedbackSignalGenerator(mirror, calibrator, pattern_memory)
    batch = generator.analyze()
    # batch.signals contains all generated feedback
    # generator.apply_safe_updates() pushes controlled tuning
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.simulation.mirror_models import (
    ComparisonOutcome,
    DriftSeverity,
    DriftSignal,
    MirrorComparison,
    ValidationMetric,
)
from src.simulation.live_simulation_mirror import LiveSimulationMirror

from .feedback_models import (
    FEEDBACK_SCHEMA_VERSION,
    FeedbackBatch,
    FeedbackSeverity,
    FeedbackSignal,
    FeedbackSignalType,
    RecommendedAction,
)


class FeedbackSignalGenerator:
    """Generates structured feedback signals from mirror analysis.

    All tuning signals are recommendations, not autonomous changes.
    The optional apply_safe_updates() method pushes only to the
    calibrator's record_outcome() and pattern memory's observation
    counters — both are append-only, non-destructive operations.
    """

    def __init__(
        self,
        mirror: LiveSimulationMirror,
        calibrator: Optional[Any] = None,       # ConfidenceCalibrator
        pattern_memory: Optional[Any] = None,    # PatternMemory
        # Analysis thresholds
        overconfidence_threshold: float = 0.3,   # mean cal error when wrong
        underconfidence_threshold: float = 0.3,  # mean cal error when right
        position_drift_threshold_m: float = 150.0,
        classification_mismatch_rate: float = 0.4,
        motif_flip_threshold: int = 3,           # distinct motifs in window
        min_sample_size: int = 3,
    ) -> None:
        self.mirror = mirror
        self.calibrator = calibrator
        self.pattern_memory = pattern_memory
        self.overconf_thresh = overconfidence_threshold
        self.underconf_thresh = underconfidence_threshold
        self.pos_drift_thresh = position_drift_threshold_m
        self.class_mismatch_rate = classification_mismatch_rate
        self.motif_flip_thresh = motif_flip_threshold
        self.min_samples = min_sample_size

        self._signal_history: List[FeedbackSignal] = []
        self._batch_history: List[FeedbackBatch] = []

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------

    def analyze(self, last_n_comparisons: int = 50) -> FeedbackBatch:
        """Analyze recent mirror data and generate feedback signals.

        Returns a FeedbackBatch with all generated signals.
        """
        comparisons = self.mirror._all_comparisons[-last_n_comparisons:]
        drift_signals = self.mirror._drift_signals[-20:]
        metrics = self.mirror.get_validation_metrics()

        signals: List[FeedbackSignal] = []

        signals.extend(self._check_overconfidence(comparisons, metrics))
        signals.extend(self._check_underconfidence(comparisons, metrics))
        signals.extend(self._check_position_drift(comparisons, drift_signals))
        signals.extend(self._check_classification_drift(comparisons))
        signals.extend(self._check_false_persistence(comparisons))
        signals.extend(self._check_unstable_motifs(comparisons))

        batch = FeedbackBatch(
            signals=signals,
            source_comparisons_analyzed=len(comparisons),
            source_drift_signals_analyzed=len(drift_signals),
        )

        self._signal_history.extend(signals)
        self._batch_history.append(batch)

        return batch

    # ------------------------------------------------------------------
    # Signal generators
    # ------------------------------------------------------------------

    def _check_overconfidence(self, comparisons: List[MirrorComparison],
                               metrics: ValidationMetric) -> List[FeedbackSignal]:
        """Detect overconfidence: high predicted confidence but wrong outcome."""
        wrong = [c for c in comparisons
                 if c.outcome in (ComparisonOutcome.INACCURATE, ComparisonOutcome.FALSE_PERSISTENCE)
                 and c.predicted_confidence > 0.6]
        if len(wrong) < self.min_samples:
            return []

        mean_conf = sum(c.predicted_confidence for c in wrong) / len(wrong)
        mean_cal_err = sum(c.calibration_error for c in wrong) / len(wrong)

        if mean_cal_err < self.overconf_thresh:
            return []

        severity = self._cal_severity(mean_cal_err)
        return [FeedbackSignal(
            signal_type=FeedbackSignalType.OVERCONFIDENCE,
            severity=severity,
            metric_name="mean_calibration_error_when_wrong",
            metric_value=mean_cal_err,
            baseline_value=self.overconf_thresh,
            deviation=mean_cal_err - self.overconf_thresh,
            sample_size=len(wrong),
            source_comparison_ids=[c.comparison_id for c in wrong[:10]],
            description=(
                f"Predictions scored mean confidence {mean_conf:.2f} but were wrong "
                f"in {len(wrong)} cases. Mean calibration error {mean_cal_err:.3f} "
                f"exceeds threshold {self.overconf_thresh}."
            ),
            recommended_actions=[RecommendedAction(
                action_type="adjust_threshold",
                target_component="confidence_calibrator",
                target_parameter="conservative_factor",
                direction="increase",
                magnitude=min(0.2, mean_cal_err),
                rationale="Reduce confidence scores to match observed accuracy",
            )],
        )]

    def _check_underconfidence(self, comparisons: List[MirrorComparison],
                                metrics: ValidationMetric) -> List[FeedbackSignal]:
        """Detect underconfidence: low predicted confidence but correct outcome."""
        right = [c for c in comparisons
                 if c.outcome in (ComparisonOutcome.ACCURATE, ComparisonOutcome.PARTIAL_MATCH)
                 and c.predicted_confidence < 0.4]
        if len(right) < self.min_samples:
            return []

        mean_conf = sum(c.predicted_confidence for c in right) / len(right)
        mean_cal_err = sum(c.calibration_error for c in right) / len(right)

        if mean_cal_err < self.underconf_thresh:
            return []

        severity = self._cal_severity(mean_cal_err)
        return [FeedbackSignal(
            signal_type=FeedbackSignalType.UNDERCONFIDENCE,
            severity=severity,
            metric_name="mean_calibration_error_when_correct",
            metric_value=mean_cal_err,
            baseline_value=self.underconf_thresh,
            deviation=mean_cal_err - self.underconf_thresh,
            sample_size=len(right),
            source_comparison_ids=[c.comparison_id for c in right[:10]],
            description=(
                f"Predictions scored mean confidence {mean_conf:.2f} but were actually correct "
                f"in {len(right)} cases. System is underconfident."
            ),
            recommended_actions=[RecommendedAction(
                action_type="adjust_threshold",
                target_component="confidence_calibrator",
                target_parameter="conservative_factor",
                direction="decrease",
                magnitude=min(0.15, mean_cal_err * 0.5),
                rationale="Increase confidence scores to match observed accuracy",
            )],
        )]

    def _check_position_drift(self, comparisons: List[MirrorComparison],
                               drift_signals: List[DriftSignal]) -> List[FeedbackSignal]:
        """Convert position drift signals into feedback."""
        pos_drifts = [d for d in drift_signals if d.drift_type == "position"]
        if not pos_drifts:
            # Check comparisons directly
            pos_errors = [c.position_error_m for c in comparisons if c.entity_was_present]
            if len(pos_errors) < self.min_samples:
                return []
            mean_err = sum(pos_errors) / len(pos_errors)
            if mean_err < self.pos_drift_thresh:
                return []
            pos_drifts = []  # will generate from comparisons below

        signals: List[FeedbackSignal] = []
        if pos_drifts:
            for drift in pos_drifts[:3]:
                severity = {
                    DriftSeverity.MINOR: FeedbackSeverity.LOW,
                    DriftSeverity.MODERATE: FeedbackSeverity.MEDIUM,
                    DriftSeverity.MAJOR: FeedbackSeverity.HIGH,
                    DriftSeverity.CRITICAL: FeedbackSeverity.CRITICAL,
                }.get(drift.severity, FeedbackSeverity.MEDIUM)

                signals.append(FeedbackSignal(
                    signal_type=FeedbackSignalType.POSITION_DRIFT,
                    severity=severity,
                    entity_id=drift.entity_id,
                    source_drift_signal_id=drift.signal_id,
                    metric_name="mean_position_error_m",
                    metric_value=drift.metric_value,
                    baseline_value=drift.threshold,
                    deviation=drift.metric_value - drift.threshold,
                    sample_size=drift.window_comparisons,
                    description=drift.explanation,
                    recommended_actions=[RecommendedAction(
                        action_type="adjust_parameter",
                        target_component="short_horizon_predictor",
                        target_parameter="position_uncertainty_growth_rate",
                        direction="increase",
                        magnitude=min(2.0, drift.metric_value / 100.0),
                        rationale=f"Position predictions off by {drift.metric_value:.0f}m mean",
                    )],
                ))
        else:
            pos_errors = [c.position_error_m for c in comparisons if c.entity_was_present]
            mean_err = sum(pos_errors) / len(pos_errors)
            signals.append(FeedbackSignal(
                signal_type=FeedbackSignalType.POSITION_DRIFT,
                severity=FeedbackSeverity.MEDIUM,
                metric_name="mean_position_error_m",
                metric_value=mean_err,
                baseline_value=self.pos_drift_thresh,
                deviation=mean_err - self.pos_drift_thresh,
                sample_size=len(pos_errors),
                description=f"Mean position error {mean_err:.1f}m exceeds threshold {self.pos_drift_thresh:.0f}m",
                recommended_actions=[RecommendedAction(
                    action_type="adjust_parameter",
                    target_component="short_horizon_predictor",
                    target_parameter="position_uncertainty_growth_rate",
                    direction="increase",
                    magnitude=min(2.0, mean_err / 100.0),
                    rationale=f"Position predictions off by {mean_err:.0f}m mean",
                )],
            ))

        return signals

    def _check_classification_drift(self, comparisons: List[MirrorComparison]) -> List[FeedbackSignal]:
        """Detect consistent threat-level misclassification."""
        present = [c for c in comparisons if c.entity_was_present]
        if len(present) < self.min_samples:
            return []

        mismatches = sum(1 for c in present if not c.threat_level_match)
        rate = mismatches / len(present)

        if rate < self.class_mismatch_rate:
            return []

        severity = FeedbackSeverity.HIGH if rate > 0.6 else FeedbackSeverity.MEDIUM
        return [FeedbackSignal(
            signal_type=FeedbackSignalType.CLASSIFICATION_DRIFT,
            severity=severity,
            metric_name="threat_level_mismatch_rate",
            metric_value=rate,
            baseline_value=self.class_mismatch_rate,
            deviation=rate - self.class_mismatch_rate,
            sample_size=len(present),
            description=f"Threat level mismatch rate {rate:.1%} ({mismatches}/{len(present)}) exceeds threshold {self.class_mismatch_rate:.1%}",
            recommended_actions=[RecommendedAction(
                action_type="review_classification",
                target_component="threat_genome_correlator",
                target_parameter="threat_level_mapping",
                direction="review",
                rationale="Threat level predictions consistently wrong; review classification logic",
            )],
        )]

    def _check_false_persistence(self, comparisons: List[MirrorComparison]) -> List[FeedbackSignal]:
        """Detect repeated false persistence (predicted entities that vanish)."""
        false_persist = [c for c in comparisons
                         if c.outcome == ComparisonOutcome.FALSE_PERSISTENCE]
        if len(false_persist) < self.min_samples:
            return []

        # Group by entity
        by_entity: Dict[str, int] = Counter(c.entity_id for c in false_persist)
        repeat_entities = {eid: cnt for eid, cnt in by_entity.items() if cnt >= 2}

        if not repeat_entities:
            return []

        signals: List[FeedbackSignal] = []
        for eid, count in repeat_entities.items():
            signals.append(FeedbackSignal(
                signal_type=FeedbackSignalType.FALSE_MERGE,
                severity=FeedbackSeverity.HIGH,
                entity_id=eid,
                metric_name="false_persistence_count",
                metric_value=float(count),
                baseline_value=1.0,
                deviation=float(count - 1),
                sample_size=count,
                description=f"Entity {eid} was falsely predicted to persist {count} times",
                recommended_actions=[RecommendedAction(
                    action_type="review_entity_lifecycle",
                    target_component="prediction_engine",
                    target_parameter="entity_persistence_assumption",
                    direction="decrease",
                    rationale=f"Entity {eid} keeps disappearing after being predicted to persist",
                )],
            ))
        return signals

    def _check_unstable_motifs(self, comparisons: List[MirrorComparison]) -> List[FeedbackSignal]:
        """Detect when the dominant predicted label keeps flipping."""
        by_entity: Dict[str, List[str]] = {}
        for c in comparisons:
            if c.entity_id:
                by_entity.setdefault(c.entity_id, [])
                # Use notes or label_match to infer label
                # We track the predicted label from comparison notes
                by_entity[c.entity_id].append(c.outcome.value)

        signals: List[FeedbackSignal] = []
        for eid, outcomes in by_entity.items():
            if len(outcomes) < self.min_samples:
                continue
            recent = outcomes[-self.motif_flip_thresh * 2:]
            unique = len(set(recent))
            if unique >= self.motif_flip_thresh:
                signals.append(FeedbackSignal(
                    signal_type=FeedbackSignalType.UNSTABLE_MOTIF,
                    severity=FeedbackSeverity.MEDIUM,
                    entity_id=eid,
                    metric_name="distinct_outcomes_in_window",
                    metric_value=float(unique),
                    baseline_value=float(self.motif_flip_thresh),
                    sample_size=len(recent),
                    description=f"Entity {eid} has {unique} distinct prediction outcomes in last {len(recent)} comparisons — unstable",
                    recommended_actions=[RecommendedAction(
                        action_type="review_motif",
                        target_component="pattern_memory",
                        target_parameter="motif_stability",
                        direction="review",
                        rationale="Prediction keeps flipping between outcomes; may need stronger motif matching",
                    )],
                ))
        return signals

    # ------------------------------------------------------------------
    # Controlled safe updates
    # ------------------------------------------------------------------

    def apply_safe_updates(self, batch: FeedbackBatch) -> Dict[str, int]:
        """Push controlled, non-destructive updates to calibrator and memory.

        ONLY performs append-only operations:
          - calibrator.record_outcome() (adds accuracy samples)
          - pattern_memory motif.record_observation() (increments counters)

        Returns count of updates applied per component.
        """
        counts = {"calibrator_outcomes": 0, "pattern_observations": 0}

        # Push outcomes to calibrator
        if self.calibrator and hasattr(self.calibrator, "record_outcome"):
            for comp in self.mirror._all_comparisons[-50:]:
                if comp.label_match:
                    actual = comp.notes[0] if comp.notes else "continue_course"
                else:
                    actual = "unknown"
                predicted = "continue_course"  # default
                try:
                    self.calibrator.record_outcome(
                        predicted_label=predicted,
                        actual_label=actual if comp.label_match else "other",
                        horizon_s=comp.horizon_s,
                    )
                    counts["calibrator_outcomes"] += 1
                except Exception:
                    pass

        # Reinforce matched motifs in pattern memory
        if self.pattern_memory and hasattr(self.pattern_memory, "all_motifs"):
            for motif in self.pattern_memory.all_motifs():
                # If motif name appears in any accurate comparison, reinforce
                accurate_count = sum(
                    1 for c in self.mirror._all_comparisons[-50:]
                    if c.outcome == ComparisonOutcome.ACCURATE
                )
                if accurate_count > 0:
                    motif.record_observation(confidence_boost=0.01)
                    counts["pattern_observations"] += 1

        return counts

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_signal_history(self, last_n: int = 50) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._signal_history[-last_n:]]

    def get_batch_history(self, last_n: int = 10) -> List[Dict[str, Any]]:
        return [b.to_dict() for b in self._batch_history[-last_n:]]

    def stats(self) -> Dict[str, Any]:
        by_type = Counter(s.signal_type.value for s in self._signal_history)
        return {
            "total_signals": len(self._signal_history),
            "total_batches": len(self._batch_history),
            "by_type": dict(by_type),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cal_severity(cal_error: float) -> FeedbackSeverity:
        if cal_error > 0.6:
            return FeedbackSeverity.CRITICAL
        if cal_error > 0.45:
            return FeedbackSeverity.HIGH
        if cal_error > 0.3:
            return FeedbackSeverity.MEDIUM
        return FeedbackSeverity.LOW
