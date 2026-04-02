# File: tests/test_short_horizon_predictor.py
"""Tests for Chunk 3: Real-Time Prediction Engine Core.

Proves:
  1. Forecast bundle returns all requested windows
  2. Uncertainty grows with longer time windows
  3. Multiple hypotheses are generated per window
  4. Supporting factors and explanation are present
  5. Stable entities forecast differently from volatile ones
  6. Escalating trend modulates hypothesis probabilities
  7. Stationary entities predict stop as dominant
  8. Request-based batch forecasting works
"""

import sys
sys.path.insert(0, ".")

import math
from datetime import datetime, timedelta, timezone

from src.prediction.prediction_models import (
    EntitySnapshot,
    ForecastBundle,
    HistoryPoint,
    MovementMode,
    PredictionHypothesis,
    PredictionRequest,
    PredictionWindow,
    ThreatPosture,
    UncertaintyEstimate,
)
from src.prediction.short_horizon_predictor import ShortHorizonPredictor


# =====================================================================
# Helpers
# =====================================================================

def _moving_entity() -> EntitySnapshot:
    """An entity moving steadily southward at 20 m/s."""
    now = datetime.now(timezone.utc)
    history = []
    for i in range(8):
        t = now - timedelta(seconds=(8 - i) * 10)
        history.append(HistoryPoint(
            timestamp=t,
            position=(100.0, 200.0 - i * 200.0, 50.0),
            velocity=(0.0, -20.0, 0.0),
            heading_deg=180.0,
            speed_mps=20.0,
            threat_level="high",
            confidence=0.8,
        ))
    return EntitySnapshot(
        entity_id="ent-mover",
        entity_type="aircraft",
        classification="hostile_uav",
        allegiance="hostile",
        position=(100.0, 200.0, 50.0),
        velocity=(0.0, -20.0, 0.0),
        heading_deg=180.0,
        speed_mps=20.0,
        threat_level="high",
        confidence=0.8,
        history=history,
    )


def _volatile_entity() -> EntitySnapshot:
    """An entity with erratic heading and speed changes."""
    now = datetime.now(timezone.utc)
    history = []
    headings = [10, 90, 350, 200, 45, 270, 130, 310]
    speeds = [5, 30, 2, 40, 8, 35, 3, 25]
    for i in range(8):
        t = now - timedelta(seconds=(8 - i) * 10)
        history.append(HistoryPoint(
            timestamp=t,
            position=(50.0 + i * 10, 100.0 - i * 5, 30.0),
            velocity=(speeds[i] * 0.7, speeds[i] * 0.7, 0.0),
            heading_deg=float(headings[i]),
            speed_mps=float(speeds[i]),
            threat_level="medium",
            confidence=0.5,
        ))
    return EntitySnapshot(
        entity_id="ent-volatile",
        entity_type="ground_vehicle",
        classification="unknown_contact",
        allegiance="unknown",
        position=(130.0, 60.0, 30.0),
        velocity=(17.5, 17.5, 0.0),
        heading_deg=310.0,
        speed_mps=25.0,
        threat_level="medium",
        confidence=0.5,
        history=history,
    )


def _stationary_entity() -> EntitySnapshot:
    """An entity that has been stationary for a while."""
    now = datetime.now(timezone.utc)
    history = []
    for i in range(5):
        t = now - timedelta(seconds=(5 - i) * 30)
        history.append(HistoryPoint(
            timestamp=t,
            position=(500.0, 500.0, 0.0),
            velocity=(0.0, 0.0, 0.0),
            heading_deg=0.0,
            speed_mps=0.0,
            threat_level="low",
            confidence=0.9,
        ))
    return EntitySnapshot(
        entity_id="ent-static",
        entity_type="location",
        classification="observation_post",
        allegiance="unknown",
        position=(500.0, 500.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        heading_deg=0.0,
        speed_mps=0.0,
        threat_level="low",
        confidence=0.9,
        history=history,
    )


def _escalating_entity() -> EntitySnapshot:
    """An entity whose threat level has been rising over time."""
    now = datetime.now(timezone.utc)
    levels = ["low", "low", "medium", "medium", "high", "high"]
    speeds = [10, 12, 15, 18, 22, 25]
    history = []
    for i in range(6):
        t = now - timedelta(seconds=(6 - i) * 20)
        history.append(HistoryPoint(
            timestamp=t,
            position=(300.0, 400.0 - i * 50, 100.0),
            velocity=(0.0, -float(speeds[i]), 0.0),
            heading_deg=180.0,
            speed_mps=float(speeds[i]),
            threat_level=levels[i],
            confidence=0.7,
        ))
    return EntitySnapshot(
        entity_id="ent-escalating",
        entity_type="aircraft",
        classification="hostile_uav",
        allegiance="hostile",
        position=(300.0, 100.0, 100.0),
        velocity=(0.0, -25.0, 0.0),
        heading_deg=180.0,
        speed_mps=25.0,
        threat_level="high",
        confidence=0.7,
        history=history,
    )


# =====================================================================
# Test 1: Forecast bundle returns all requested windows
# =====================================================================

def test_forecast_returns_all_windows():
    predictor = ShortHorizonPredictor()
    entity = _moving_entity()
    bundle = predictor.forecast(entity, windows_s=[30.0, 120.0, 600.0])

    assert isinstance(bundle, ForecastBundle)
    assert bundle.entity_id == "ent-mover"
    assert len(bundle.windows) == 3

    window_secs = [w.window_seconds for w in bundle.windows]
    assert 30.0 in window_secs
    assert 120.0 in window_secs
    assert 600.0 in window_secs

    # Each window has hypotheses
    for w in bundle.windows:
        assert len(w.hypotheses) >= 1, f"Window {w.window_label} has no hypotheses"
        assert w.dominant_hypothesis_id is not None

    # Bundle has metadata
    assert bundle.bundle_id != ""
    assert bundle.entity_classification == "hostile_uav"
    assert 0.0 <= bundle.forecast_confidence <= 1.0

    # Serialization
    d = bundle.to_dict()
    assert d["window_count"] == 3
    assert len(d["windows"]) == 3

    print("PASS: Forecast bundle returns all requested windows")


# =====================================================================
# Test 2: Uncertainty grows with longer time windows
# =====================================================================

def test_uncertainty_grows_with_horizon():
    predictor = ShortHorizonPredictor()
    entity = _moving_entity()
    bundle = predictor.forecast(entity, windows_s=[30.0, 120.0, 600.0])

    w30 = bundle.get_window(30.0)
    w120 = bundle.get_window(120.0)
    w600 = bundle.get_window(600.0)

    assert w30 is not None and w120 is not None and w600 is not None

    u30 = w30.aggregate_uncertainty
    u120 = w120.aggregate_uncertainty
    u600 = w600.aggregate_uncertainty

    assert u30 is not None and u120 is not None and u600 is not None

    # Spatial uncertainty must grow monotonically
    assert u120.spatial_radius_m > u30.spatial_radius_m, \
        f"120s uncertainty ({u120.spatial_radius_m}) must > 30s ({u30.spatial_radius_m})"
    assert u600.spatial_radius_m > u120.spatial_radius_m, \
        f"600s uncertainty ({u600.spatial_radius_m}) must > 120s ({u120.spatial_radius_m})"

    # Temporal confidence must decay monotonically
    assert u120.temporal_confidence < u30.temporal_confidence, \
        f"120s confidence ({u120.temporal_confidence}) must < 30s ({u30.temporal_confidence})"
    assert u600.temporal_confidence < u120.temporal_confidence, \
        f"600s confidence ({u600.temporal_confidence}) must < 120s ({u120.temporal_confidence})"

    print("PASS: Uncertainty grows with longer time windows")


# =====================================================================
# Test 3: Multiple hypotheses generated
# =====================================================================

def test_multiple_hypotheses_generated():
    predictor = ShortHorizonPredictor(max_hypotheses=5)
    entity = _moving_entity()
    bundle = predictor.forecast(entity)

    for w in bundle.windows:
        assert len(w.hypotheses) >= 2, \
            f"Window {w.window_label} should have >=2 hypotheses, got {len(w.hypotheses)}"
        assert len(w.hypotheses) <= 5

        # Probabilities should sum to ~1.0
        total_p = sum(h.probability for h in w.hypotheses)
        assert abs(total_p - 1.0) < 0.05, \
            f"Window {w.window_label} probabilities sum to {total_p}, expected ~1.0"

        # Each hypothesis has a label
        labels = [h.label for h in w.hypotheses]
        assert all(label != "" for label in labels)

        # Each hypothesis has a predicted state
        for h in w.hypotheses:
            assert h.predicted_state is not None
            assert h.uncertainty is not None

    print("PASS: Multiple hypotheses generated per window")


# =====================================================================
# Test 4: Supporting factors and explanation present
# =====================================================================

def test_explanation_present():
    predictor = ShortHorizonPredictor()
    entity = _moving_entity()
    bundle = predictor.forecast(entity, windows_s=[60.0])

    w = bundle.get_window(60.0)
    assert w is not None

    for h in w.hypotheses:
        exp = h.explanation
        assert exp is not None
        assert len(exp.primary_factors) >= 1, "Must have at least 1 primary factor"
        assert len(exp.supporting_observations) >= 1, "Must have at least 1 supporting observation"
        assert exp.methodology != "", "Methodology must be stated"

        # Serialization
        d = exp.to_dict()
        assert "primary_factors" in d
        assert "supporting_observations" in d
        assert "uncertainty_notes" in d
        assert "methodology" in d

    print("PASS: Supporting factors and explanations present in all hypotheses")


# =====================================================================
# Test 5: Stable entities forecast differently from volatile ones
# =====================================================================

def test_stable_vs_volatile():
    predictor = ShortHorizonPredictor()

    stable = _moving_entity()
    volatile = _volatile_entity()

    bundle_stable = predictor.forecast(stable, windows_s=[120.0])
    bundle_volatile = predictor.forecast(volatile, windows_s=[120.0])

    # Volatile entity should have higher volatility score
    assert bundle_volatile.volatility_score > bundle_stable.volatility_score, \
        f"Volatile ({bundle_volatile.volatility_score}) should > stable ({bundle_stable.volatility_score})"

    # Volatile entity should have wider uncertainty
    w_stable = bundle_stable.get_window(120.0)
    w_volatile = bundle_volatile.get_window(120.0)
    assert w_stable is not None and w_volatile is not None

    u_stable = w_stable.aggregate_uncertainty
    u_volatile = w_volatile.aggregate_uncertainty
    assert u_volatile.spatial_radius_m > u_stable.spatial_radius_m, \
        f"Volatile spatial uncertainty ({u_volatile.spatial_radius_m}) must > stable ({u_stable.spatial_radius_m})"

    # Volatile entity: "continue_course" should have lower probability
    # than for the stable entity
    def _get_continue_prob(window):
        for h in window.hypotheses:
            if h.label == "continue_course":
                return h.probability
        return 0.0

    stable_continue = _get_continue_prob(w_stable)
    volatile_continue = _get_continue_prob(w_volatile)
    assert volatile_continue < stable_continue, \
        f"Volatile continue_course ({volatile_continue:.3f}) should < stable ({stable_continue:.3f})"

    # Volatile entity should have lower overall forecast confidence
    assert bundle_volatile.forecast_confidence < bundle_stable.forecast_confidence

    print("PASS: Stable entities forecast differently from volatile ones")


# =====================================================================
# Test 6: Escalating trend modulates probabilities
# =====================================================================

def test_escalating_trend():
    predictor = ShortHorizonPredictor()
    entity = _escalating_entity()
    bundle = predictor.forecast(entity, windows_s=[120.0])

    assert bundle.overall_trend == ThreatPosture.ESCALATING, \
        f"Expected ESCALATING trend, got {bundle.overall_trend.value}"

    w = bundle.get_window(120.0)
    assert w is not None

    # For an escalating entity, accelerate + continue should be favored
    probs = {h.label: h.probability for h in w.hypotheses}
    continue_p = probs.get("continue_course", 0)
    stop_p = probs.get("stop", 0)
    reverse_p = probs.get("reverse", 0)

    # Continue/accelerate should dominate over stop/reverse
    assert continue_p > stop_p, \
        f"Escalating: continue ({continue_p:.3f}) should > stop ({stop_p:.3f})"

    # Threat level projection should maintain or escalate
    dominant = w.dominant
    assert dominant is not None
    assert dominant.predicted_state.predicted_threat_level in ("high", "critical"), \
        f"Expected high/critical, got {dominant.predicted_state.predicted_threat_level}"

    print("PASS: Escalating trend modulates hypothesis probabilities")


# =====================================================================
# Test 7: Stationary entity predicts stop as dominant
# =====================================================================

def test_stationary_entity():
    predictor = ShortHorizonPredictor()
    entity = _stationary_entity()
    bundle = predictor.forecast(entity, windows_s=[30.0, 120.0])

    for w in bundle.windows:
        dominant = w.dominant
        assert dominant is not None
        assert dominant.label == "stop", \
            f"Stationary entity dominant should be 'stop', got '{dominant.label}'"
        assert dominant.predicted_state.predicted_speed_mps < 1.0

    # Position should barely change
    w30 = bundle.get_window(30.0)
    assert w30 is not None
    dom = w30.dominant
    assert dom is not None
    dist = math.sqrt(
        (dom.predicted_state.predicted_position[0] - entity.position[0]) ** 2 +
        (dom.predicted_state.predicted_position[1] - entity.position[1]) ** 2
    )
    assert dist < 5.0, f"Stationary entity should barely move, moved {dist:.1f}m"

    print("PASS: Stationary entity predicts stop as dominant")


# =====================================================================
# Test 8: Request-based batch forecasting
# =====================================================================

def test_batch_forecast():
    predictor = ShortHorizonPredictor()
    request = PredictionRequest(
        entities=[_moving_entity(), _stationary_entity(), _volatile_entity()],
        windows_seconds=[30.0, 120.0],
        max_hypotheses=4,
    )

    bundles = predictor.forecast_from_request(request)
    assert len(bundles) == 3

    for bundle in bundles:
        assert bundle.request_id == request.request_id
        assert len(bundle.windows) == 2
        for w in bundle.windows:
            assert len(w.hypotheses) >= 1
            assert len(w.hypotheses) <= 4

    # Different entities should produce different forecasts
    ids = [b.entity_id for b in bundles]
    assert len(set(ids)) == 3, "All three entities should produce distinct bundles"

    print("PASS: Request-based batch forecasting works")


# =====================================================================
# Run all tests
# =====================================================================

if __name__ == "__main__":
    test_forecast_returns_all_windows()
    test_uncertainty_grows_with_horizon()
    test_multiple_hypotheses_generated()
    test_explanation_present()
    test_stable_vs_volatile()
    test_escalating_trend()
    test_stationary_entity()
    test_batch_forecast()
    print("\nAll Short-Horizon Predictor tests passed")
