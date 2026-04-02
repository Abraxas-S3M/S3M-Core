# File: tests/test_feedback_signal_generator.py
"""Tests for Chunk 7: Continuous Learning Feedback Interface.

Proves:
  1. Underconfidence signal generated when low-conf predictions are correct
  2. Overconfidence signal generated when high-conf predictions are wrong
  3. Position drift creates appropriate refinement signal
  4. False persistence patterns create corrective output
  5. Feedback objects are versioned and traceable
  6. Classification drift detected
  7. Safe updates push to calibrator without code rewriting
  8. Batch analysis produces structured summary
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone

from src.simulation.mirror_models import (
    ComparisonOutcome,
    DriftSeverity,
    DriftSignal,
    MirrorComparison,
    ObservedStateFrame,
    PredictedStateFrame,
    ValidationMetric,
)
from src.simulation.live_simulation_mirror import LiveSimulationMirror
from src.learning.feedback_models import (
    FEEDBACK_SCHEMA_VERSION,
    FeedbackBatch,
    FeedbackSeverity,
    FeedbackSignal,
    FeedbackSignalType,
    FeedbackStatus,
    RecommendedAction,
)
from src.learning.feedback_signal_generator import FeedbackSignalGenerator


# =====================================================================
# Helpers
# =====================================================================

def _now():
    return datetime.now(timezone.utc)


def _pred(eid, pos, confidence=0.7, threat="high", label="continue_course",
           horizon_s=30.0, offset_s=30.0):
    now = _now()
    return PredictedStateFrame(
        entity_id=eid,
        prediction_timestamp=now,
        target_timestamp=now + timedelta(seconds=offset_s),
        horizon_s=horizon_s,
        predicted_position=pos,
        predicted_heading_deg=180.0,
        predicted_speed_mps=20.0,
        predicted_threat_level=threat,
        predicted_label=label,
        predicted_confidence=confidence,
    )


def _obs(eid, pos, threat="high", speed=20.0, present=True, offset_s=30.0):
    return ObservedStateFrame(
        entity_id=eid,
        observation_timestamp=_now() + timedelta(seconds=offset_s),
        observed_position=pos,
        observed_heading_deg=180.0,
        observed_speed_mps=speed,
        observed_threat_level=threat,
        entity_present=present,
    )


def _build_mirror_with_overconfident_wrong() -> LiveSimulationMirror:
    """Mirror where high-confidence predictions are consistently wrong."""
    mirror = LiveSimulationMirror(position_accurate_m=50.0, position_partial_m=200.0)
    for i in range(6):
        p = _pred(f"oc-{i}", (100.0, 200.0, 50.0), confidence=0.85,
                   threat="high", offset_s=float(i))
        mirror.record_prediction(p)
        o = _obs(f"oc-{i}", (500.0, 600.0, 50.0), threat="low",
                  offset_s=float(i))
        mirror.record_observation(o)
    return mirror


def _build_mirror_with_underconfident_right() -> LiveSimulationMirror:
    """Mirror where low-confidence predictions are consistently correct."""
    mirror = LiveSimulationMirror(position_accurate_m=50.0)
    for i in range(6):
        p = _pred(f"uc-{i}", (100.0, 200.0, 50.0), confidence=0.2,
                   threat="high", offset_s=float(i))
        mirror.record_prediction(p)
        o = _obs(f"uc-{i}", (105.0, 195.0, 50.0), threat="high",
                  offset_s=float(i))
        mirror.record_observation(o)
    return mirror


def _build_mirror_with_position_drift() -> LiveSimulationMirror:
    """Mirror with consistent large position errors triggering drift."""
    mirror = LiveSimulationMirror(
        position_accurate_m=50.0,
        drift_window_size=5,
        drift_position_threshold_m=100.0,
    )
    for i in range(7):
        p = _pred("drift-ent", (100.0, 200.0, 50.0), offset_s=float(i))
        mirror.record_prediction(p)
        o = _obs("drift-ent", (400.0, 500.0, 50.0), offset_s=float(i))
        mirror.record_observation(o)
    mirror.detect_drift("drift-ent")
    return mirror


def _build_mirror_with_false_persistence() -> LiveSimulationMirror:
    """Mirror where predicted entities repeatedly disappear."""
    mirror = LiveSimulationMirror()
    for i in range(4):
        p = _pred("ghost-ent", (100.0, 200.0, 50.0), confidence=0.8,
                   offset_s=float(i))
        mirror.record_prediction(p)
        mirror.record_entity_disappeared("ghost-ent")
    return mirror


# =====================================================================
# Test 1: Underconfidence signal
# =====================================================================

def test_underconfidence_signal():
    mirror = _build_mirror_with_underconfident_right()
    gen = FeedbackSignalGenerator(mirror, min_sample_size=3)
    batch = gen.analyze()

    under = batch.by_type(FeedbackSignalType.UNDERCONFIDENCE)
    assert len(under) >= 1, f"Expected underconfidence signal, got types: {[s.signal_type.value for s in batch.signals]}"

    sig = under[0]
    assert sig.signal_type == FeedbackSignalType.UNDERCONFIDENCE
    assert sig.sample_size >= 3
    assert sig.metric_value > 0
    assert sig.description != ""
    assert len(sig.recommended_actions) >= 1

    # Recommended action should decrease conservative factor
    action = sig.recommended_actions[0]
    assert action.direction == "decrease"
    assert action.target_component == "confidence_calibrator"

    print("PASS: Underconfidence signal generated correctly")


# =====================================================================
# Test 2: Overconfidence signal
# =====================================================================

def test_overconfidence_signal():
    mirror = _build_mirror_with_overconfident_wrong()
    gen = FeedbackSignalGenerator(mirror, min_sample_size=3)
    batch = gen.analyze()

    over = batch.by_type(FeedbackSignalType.OVERCONFIDENCE)
    assert len(over) >= 1, f"Expected overconfidence signal, got types: {[s.signal_type.value for s in batch.signals]}"

    sig = over[0]
    assert sig.signal_type == FeedbackSignalType.OVERCONFIDENCE
    assert sig.sample_size >= 3
    assert sig.metric_value > 0

    # Recommended action should increase conservative factor
    action = sig.recommended_actions[0]
    assert action.direction == "increase"
    assert action.target_component == "confidence_calibrator"

    print("PASS: Overconfidence signal generated correctly")


# =====================================================================
# Test 3: Drift creates refinement signal
# =====================================================================

def test_drift_refinement_signal():
    mirror = _build_mirror_with_position_drift()
    gen = FeedbackSignalGenerator(mirror, min_sample_size=3,
                                   position_drift_threshold_m=100.0)
    batch = gen.analyze()

    pos_drift = batch.by_type(FeedbackSignalType.POSITION_DRIFT)
    assert len(pos_drift) >= 1, f"Expected position drift signal, got types: {[s.signal_type.value for s in batch.signals]}"

    sig = pos_drift[0]
    assert sig.signal_type == FeedbackSignalType.POSITION_DRIFT
    assert sig.metric_value > 100.0
    assert sig.entity_id == "drift-ent"

    # Should recommend increasing position uncertainty
    action = sig.recommended_actions[0]
    assert action.direction == "increase"
    assert "position" in action.target_parameter.lower()

    print("PASS: Position drift creates refinement signal")


# =====================================================================
# Test 4: False persistence creates corrective output
# =====================================================================

def test_false_persistence_signal():
    mirror = _build_mirror_with_false_persistence()
    gen = FeedbackSignalGenerator(mirror, min_sample_size=2)
    batch = gen.analyze()

    fp = batch.by_type(FeedbackSignalType.FALSE_MERGE)
    assert len(fp) >= 1, f"Expected false_merge signal, got types: {[s.signal_type.value for s in batch.signals]}"

    sig = fp[0]
    assert sig.entity_id == "ghost-ent"
    assert sig.metric_value >= 2.0
    assert sig.severity in (FeedbackSeverity.HIGH, FeedbackSeverity.CRITICAL)

    action = sig.recommended_actions[0]
    assert "persistence" in action.target_parameter.lower() or "lifecycle" in action.action_type.lower()

    print("PASS: False persistence creates corrective output")


# =====================================================================
# Test 5: Feedback objects are versioned and traceable
# =====================================================================

def test_versioned_and_traceable():
    mirror = _build_mirror_with_overconfident_wrong()
    gen = FeedbackSignalGenerator(mirror, min_sample_size=3)
    batch = gen.analyze()

    # Batch is versioned
    assert batch.schema_version == FEEDBACK_SCHEMA_VERSION
    assert batch.batch_id.startswith("batch-")
    assert batch.generated_at is not None

    # Each signal is versioned and has unique ID
    for sig in batch.signals:
        assert sig.schema_version == FEEDBACK_SCHEMA_VERSION
        assert sig.signal_id.startswith("fbs-")
        assert sig.status == FeedbackStatus.PENDING
        assert sig.generated_at is not None

    # Serialization round-trip
    d = batch.to_dict()
    assert d["schema_version"] == FEEDBACK_SCHEMA_VERSION
    assert "signals" in d
    assert "summary" in d
    assert d["source_comparisons_analyzed"] >= 3

    # Each signal serializes with all fields
    for sig_dict in d["signals"]:
        assert "signal_id" in sig_dict
        assert "schema_version" in sig_dict
        assert "signal_type" in sig_dict
        assert "severity" in sig_dict
        assert "metric_value" in sig_dict
        assert "recommended_actions" in sig_dict

    # Source comparison IDs are traceable
    for sig in batch.signals:
        if sig.source_comparison_ids:
            assert all(isinstance(cid, str) for cid in sig.source_comparison_ids)

    print("PASS: Feedback objects are versioned and traceable")


# =====================================================================
# Test 6: Classification drift detected
# =====================================================================

def test_classification_drift():
    mirror = LiveSimulationMirror(position_accurate_m=50.0)
    # Predictions say "high" threat, observations say "low"
    for i in range(6):
        p = _pred(f"cd-{i}", (100.0, 200.0, 50.0), confidence=0.6,
                   threat="high", offset_s=float(i))
        mirror.record_prediction(p)
        o = _obs(f"cd-{i}", (105.0, 195.0, 50.0), threat="low",
                  offset_s=float(i))
        mirror.record_observation(o)

    gen = FeedbackSignalGenerator(mirror, min_sample_size=3,
                                   classification_mismatch_rate=0.4)
    batch = gen.analyze()

    cls_drift = batch.by_type(FeedbackSignalType.CLASSIFICATION_DRIFT)
    assert len(cls_drift) >= 1, f"Expected classification_drift, got types: {[s.signal_type.value for s in batch.signals]}"

    sig = cls_drift[0]
    assert sig.metric_value > 0.4
    assert "mismatch" in sig.description.lower()

    print("PASS: Classification drift detected correctly")


# =====================================================================
# Test 7: Safe updates push to calibrator
# =====================================================================

def test_safe_updates():
    mirror = _build_mirror_with_overconfident_wrong()

    # Create a mock calibrator with record_outcome
    class MockCalibrator:
        def __init__(self):
            self.outcomes = []
        def record_outcome(self, predicted_label, actual_label, horizon_s):
            self.outcomes.append((predicted_label, actual_label, horizon_s))

    calibrator = MockCalibrator()
    gen = FeedbackSignalGenerator(mirror, calibrator=calibrator, min_sample_size=3)
    batch = gen.analyze()

    counts = gen.apply_safe_updates(batch)
    assert counts["calibrator_outcomes"] > 0, "Should push outcomes to calibrator"
    assert len(calibrator.outcomes) > 0, "Calibrator should have received outcomes"

    # Calibrator outcomes are tuples, not code rewrites
    for outcome in calibrator.outcomes:
        assert len(outcome) == 3  # (predicted, actual, horizon)

    print("PASS: Safe updates push to calibrator without code rewriting")


# =====================================================================
# Test 8: Batch analysis produces structured summary
# =====================================================================

def test_batch_summary():
    mirror = _build_mirror_with_overconfident_wrong()
    gen = FeedbackSignalGenerator(mirror, min_sample_size=3)
    batch = gen.analyze()

    assert batch.signal_count >= 1
    assert batch.source_comparisons_analyzed >= 3

    # Summary should list signal types present
    d = batch.to_dict()
    summary = d["summary"]
    assert isinstance(summary, dict)
    # At least one type should be present
    assert len(summary) >= 1

    # By severity filter
    medium_plus = batch.by_severity(FeedbackSeverity.MEDIUM)
    assert isinstance(medium_plus, list)

    # Stats from generator
    stats = gen.stats()
    assert stats["total_signals"] >= 1
    assert stats["total_batches"] == 1

    # History
    history = gen.get_signal_history()
    assert len(history) >= 1
    assert all("signal_id" in h for h in history)

    print("PASS: Batch analysis produces structured summary")


# =====================================================================
# Run all tests
# =====================================================================

if __name__ == "__main__":
    test_underconfidence_signal()
    test_overconfidence_signal()
    test_drift_refinement_signal()
    test_false_persistence_signal()
    test_versioned_and_traceable()
    test_classification_drift()
    test_safe_updates()
    test_batch_summary()
    print("\nAll Feedback Signal Generator tests passed")
