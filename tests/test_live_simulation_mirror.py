"""Tests for Chunk 6: Live Simulation Mirror Core.

Proves:
  1. Mirror stores predicted and observed frames correctly
  2. Comparison metrics compute correctly (position error, heading, threat match)
  3. Accurate prediction is classified as ACCURATE
  4. Large position error is classified as INACCURATE
  5. Drift signals generated when predictions consistently diverge
  6. Validation metrics accumulate over time
  7. False persistence detected when predicted entity disappears
  8. Feedback output generated with recommended adjustments
"""

import math
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from src.simulation.live_simulation_mirror import LiveSimulationMirror
from src.simulation.mirror_models import DriftSeverity, PredictedStateFrame, ObservedStateFrame


# =====================================================================
# Helpers
# =====================================================================


def _now():
    return datetime.now(timezone.utc)


def _pred(
    entity_id: str,
    position: tuple,
    heading: float = 180.0,
    speed: float = 20.0,
    threat: str = "high",
    confidence: float = 0.7,
    label: str = "continue_course",
    horizon_s: float = 30.0,
    target_offset_s: float = 30.0,
):
    now = _now()
    return PredictedStateFrame(
        entity_id=entity_id,
        prediction_timestamp=now,
        target_timestamp=now + timedelta(seconds=target_offset_s),
        horizon_s=horizon_s,
        predicted_position=position,
        predicted_velocity=(0.0, -speed, 0.0),
        predicted_heading_deg=heading,
        predicted_speed_mps=speed,
        predicted_threat_level=threat,
        predicted_label=label,
        predicted_confidence=confidence,
    )


def _obs(
    entity_id: str,
    position: tuple,
    heading: float = 180.0,
    speed: float = 20.0,
    threat: str = "high",
    confidence: float = 0.8,
    present: bool = True,
    time_offset_s: float = 30.0,
):
    return ObservedStateFrame(
        entity_id=entity_id,
        observation_timestamp=_now() + timedelta(seconds=time_offset_s),
        observed_position=position,
        observed_velocity=(0.0, -speed, 0.0),
        observed_heading_deg=heading,
        observed_speed_mps=speed,
        observed_threat_level=threat,
        observed_confidence=confidence,
        entity_present=present,
    )


# =====================================================================
# Test 1: Mirror stores predicted and observed frames
# =====================================================================


def test_stores_frames():
    mirror = LiveSimulationMirror()

    pred = _pred("ent-001", (100.0, 200.0, 50.0))
    mirror.record_prediction(pred)

    assert mirror.stats()["pending_predictions"] == 1

    obs = _obs("ent-001", (110.0, 190.0, 50.0))
    mirror.record_observation(obs)

    assert mirror.stats()["total_frames"] == 1
    assert mirror.stats()["total_comparisons"] == 1

    frames = mirror.get_frames("ent-001")
    assert len(frames) == 1
    assert frames[0]["is_complete"] is True
    assert frames[0]["predicted"] is not None
    assert frames[0]["observed"] is not None
    assert frames[0]["comparison"] is not None

    print("PASS: Mirror stores predicted and observed frames correctly")


# =====================================================================
# Test 2: Comparison metrics compute correctly
# =====================================================================


def test_comparison_metrics():
    mirror = LiveSimulationMirror()

    pred = _pred("ent-002", (100.0, 200.0, 50.0), heading=180.0, speed=20.0, threat="high")
    mirror.record_prediction(pred)

    obs = _obs("ent-002", (120.0, 180.0, 50.0), heading=190.0, speed=18.0, threat="high")
    mirror.record_observation(obs)

    frames = mirror.get_frames("ent-002")
    comp = frames[0]["comparison"]

    # Position error: sqrt(20^2 + 20^2) ≈ 28.28
    expected_pos_err = math.sqrt(20**2 + 20**2)
    assert abs(comp["position_error_m"] - expected_pos_err) < 1.0, (
        f"Position error should be ~{expected_pos_err:.1f}, got {comp['position_error_m']}"
    )

    # Heading error: 10 degrees
    assert abs(comp["heading_error_deg"] - 10.0) < 0.5

    # Speed error: 2 m/s
    assert abs(comp["speed_error_mps"] - 2.0) < 0.5

    # Threat match: both "high"
    assert comp["threat_level_match"] is True

    # Calibration error should be present
    assert "calibration_error" in comp

    print("PASS: Comparison metrics compute correctly")


# =====================================================================
# Test 3: Accurate prediction classified correctly
# =====================================================================


def test_accurate_prediction():
    mirror = LiveSimulationMirror(position_accurate_m=50.0)

    # Predict and observe very close positions
    pred = _pred("ent-003", (100.0, 200.0, 50.0), threat="high")
    mirror.record_prediction(pred)

    obs = _obs("ent-003", (105.0, 195.0, 50.0), threat="high")
    mirror.record_observation(obs)

    frames = mirror.get_frames("ent-003")
    comp = frames[0]["comparison"]

    # Position error ~7.07m, well under 50m threshold
    assert comp["outcome"] == "accurate", (
        f"Expected 'accurate', got '{comp['outcome']}' (pos_err={comp['position_error_m']:.1f})"
    )
    assert comp["position_error_m"] < 50.0

    print("PASS: Accurate prediction classified as ACCURATE")


# =====================================================================
# Test 4: Large position error classified as INACCURATE
# =====================================================================


def test_inaccurate_prediction():
    mirror = LiveSimulationMirror(position_accurate_m=50.0, position_partial_m=200.0)

    pred = _pred("ent-004", (100.0, 200.0, 50.0), threat="high")
    mirror.record_prediction(pred)

    # Observed 500m away
    obs = _obs("ent-004", (500.0, 500.0, 50.0), threat="medium")
    mirror.record_observation(obs)

    frames = mirror.get_frames("ent-004")
    comp = frames[0]["comparison"]

    assert comp["outcome"] == "inaccurate", f"Expected 'inaccurate', got '{comp['outcome']}'"
    assert comp["position_error_m"] > 200.0
    assert comp["threat_level_match"] is False

    print("PASS: Large position error classified as INACCURATE")


# =====================================================================
# Test 5: Drift signals generated
# =====================================================================


def test_drift_detection():
    mirror = LiveSimulationMirror(
        drift_window_size=5,
        drift_position_threshold_m=100.0,
    )

    # Record 6 consistently bad predictions
    for i in range(6):
        pred = _pred(
            "ent-drift",
            (100.0, 200.0, 50.0),
            target_offset_s=float(i),
        )
        mirror.record_prediction(pred)

        # Observed 300m away each time
        obs = _obs(
            "ent-drift",
            (400.0, 200.0, 50.0),
            time_offset_s=float(i),
        )
        mirror.record_observation(obs)

    signals = mirror.detect_drift("ent-drift")
    assert len(signals) >= 1, "Should generate at least one drift signal"

    pos_drifts = [s for s in signals if s.drift_type == "position"]
    assert len(pos_drifts) >= 1, "Should detect position drift"
    assert pos_drifts[0].metric_value > 100.0
    assert pos_drifts[0].severity in (
        DriftSeverity.MODERATE,
        DriftSeverity.MAJOR,
        DriftSeverity.CRITICAL,
    )
    assert pos_drifts[0].explanation != ""
    assert pos_drifts[0].window_comparisons >= 2

    # Serialization
    d = pos_drifts[0].to_dict()
    assert "severity" in d
    assert "explanation" in d
    assert "metric_value" in d

    # Global drift signals log
    all_signals = mirror.get_drift_signals()
    assert len(all_signals) >= 1

    print("PASS: Drift signals generated when predictions consistently diverge")


# =====================================================================
# Test 6: Validation metrics accumulate
# =====================================================================


def test_validation_metrics():
    mirror = LiveSimulationMirror(position_accurate_m=50.0)

    # 5 accurate predictions
    for i in range(5):
        pred = _pred(
            f"ent-val-{i}",
            (100.0, 200.0, 50.0),
            threat="high",
            label="continue_course",
            target_offset_s=float(i),
        )
        mirror.record_prediction(pred)
        obs = _obs(
            f"ent-val-{i}",
            (105.0 + i, 195.0, 50.0),
            threat="high",
            speed=20.0,
            time_offset_s=float(i),
        )
        mirror.record_observation(obs)

    # 2 inaccurate predictions
    for i in range(2):
        pred = _pred(
            f"ent-bad-{i}",
            (100.0, 200.0, 50.0),
            threat="high",
            confidence=0.8,
            target_offset_s=float(i),
        )
        mirror.record_prediction(pred)
        obs = _obs(
            f"ent-bad-{i}",
            (500.0, 500.0, 50.0),
            threat="low",
            time_offset_s=float(i),
        )
        mirror.record_observation(obs)

    metrics = mirror.get_validation_metrics()

    assert metrics.total_comparisons == 7
    assert metrics.mean_position_error_m > 0
    assert metrics.max_position_error_m > metrics.mean_position_error_m
    assert 0.0 <= metrics.label_precision <= 1.0
    assert 0.0 <= metrics.detection_recall <= 1.0
    assert 0.0 <= metrics.mean_calibration_error <= 1.0

    # Serialization
    d = metrics.to_dict()
    assert d["total_comparisons"] == 7
    assert "label_precision" in d
    assert "mean_position_error_m" in d

    print("PASS: Validation metrics accumulate over time")


# =====================================================================
# Test 7: False persistence detected
# =====================================================================


def test_false_persistence():
    mirror = LiveSimulationMirror()

    # Predict entity exists
    pred = _pred("ent-ghost", (100.0, 200.0, 50.0), confidence=0.8)
    mirror.record_prediction(pred)

    # Entity disappears
    mirror.record_entity_disappeared("ent-ghost")

    frames = mirror.get_frames("ent-ghost")
    assert len(frames) >= 1

    comp = frames[0]["comparison"]
    assert comp["outcome"] == "false_persistence", (
        f"Expected 'false_persistence', got '{comp['outcome']}'"
    )
    assert comp["calibration_error"] > 0, "Should have calibration error for missed prediction"
    assert "false persistence" in comp["notes"][0].lower()

    print("PASS: False persistence detected when predicted entity disappears")


# =====================================================================
# Test 8: Feedback output generated
# =====================================================================


def test_feedback_generation():
    mirror = LiveSimulationMirror(position_accurate_m=50.0, position_partial_m=200.0)

    # Record a bad prediction to trigger feedback adjustments
    pred = _pred("ent-fb", (100.0, 200.0, 50.0), confidence=0.9, threat="high")
    mirror.record_prediction(pred)
    obs = _obs("ent-fb", (600.0, 600.0, 50.0), threat="low")
    mirror.record_observation(obs)

    feedback = mirror.generate_feedback(last_n=10)
    assert len(feedback) >= 1

    fb = feedback[0]
    assert fb.position_error_m > 200.0
    assert fb.calibration_error > 0

    # Should recommend adjustments for large errors
    adj = fb.recommended_adjustments
    assert "increase_position_uncertainty" in adj or "recalibrate_confidence" in adj, (
        f"Should recommend adjustments, got {adj}"
    )

    # Serialization
    d = fb.to_dict()
    assert "recommended_adjustments" in d
    assert "position_error_m" in d

    # Stats should reflect feedback
    stats = mirror.stats()
    assert stats["feedback_items"] >= 1

    print("PASS: Feedback output generated with recommended adjustments")


# =====================================================================
# Run all tests
# =====================================================================


if __name__ == "__main__":
    test_stores_frames()
    test_comparison_metrics()
    test_accurate_prediction()
    test_inaccurate_prediction()
    test_drift_detection()
    test_validation_metrics()
    test_false_persistence()
    test_feedback_generation()
    print("\nAll Live Simulation Mirror tests passed")
