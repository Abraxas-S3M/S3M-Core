"""Tests for short-horizon predictor with Chunk 4 compatibility.

This suite preserves backward-compatibility expectations while validating
optional pattern-memory and confidence calibration integration.
"""

import sys

sys.path.insert(0, ".")

from src.prediction.confidence_calibrator import ConfidenceCalibrator
from src.prediction.pattern_memory import PatternMemory
from src.prediction.prediction_models import EntitySnapshot, HistoricalObservation, ThreatPosture
from src.prediction.short_horizon_predictor import ShortHorizonPredictor


def _entity_with_history() -> EntitySnapshot:
    history = [
        HistoricalObservation(
            timestamp_s=float(i),
            position=(1000.0 - 25.0 * i, 400.0 + 2.0 * i, 1200.0),
            speed_mps=20.0 + i,
            heading_deg=45.0 + (i % 3),
            threat_level="medium" if i < 2 else "high",
        )
        for i in range(5)
    ]
    return EntitySnapshot(
        entity_id="ent-1",
        entity_type="aircraft",
        position=(860.0, 420.0, 1200.0),
        speed_mps=25.0,
        heading_deg=46.0,
        threat_level="high",
        behavior_tags=["hostile"],
        confidence=0.82,
        volatility=0.25,
        history=history,
    )


def test_forecast_without_optional_components() -> None:
    predictor = ShortHorizonPredictor()
    entity = _entity_with_history()
    bundle = predictor.forecast(entity)

    assert bundle.entity_id == entity.entity_id
    assert len(bundle.windows) == 3
    assert bundle.calibration_applied is False
    assert bundle.matched_motif_name is None
    assert bundle.motif_match_score == 0.0


def test_window_and_hypothesis_counts() -> None:
    predictor = ShortHorizonPredictor(windows_s=[15.0, 45.0], top_hypotheses_per_window=2)
    bundle = predictor.forecast(_entity_with_history())
    assert len(bundle.windows) == 2
    assert all(len(w.hypotheses) == 2 for w in bundle.windows)


def test_probabilities_are_bounded() -> None:
    predictor = ShortHorizonPredictor()
    bundle = predictor.forecast(_entity_with_history())
    for window in bundle.windows:
        for hyp in window.hypotheses:
            assert 0.0 <= hyp.probability <= 1.0


def test_trend_inference_escalating() -> None:
    predictor = ShortHorizonPredictor()
    bundle = predictor.forecast(_entity_with_history())
    assert bundle.overall_trend in {ThreatPosture.ESCALATING, ThreatPosture.STABLE}


def test_to_dict_contains_chunk4_bundle_fields() -> None:
    predictor = ShortHorizonPredictor()
    payload = predictor.forecast(_entity_with_history()).to_dict()
    assert "matched_motif" in payload
    assert "motif_match_score" in payload
    assert "calibration_applied" in payload


def test_pattern_memory_integration_sets_motif_metadata() -> None:
    memory = PatternMemory()
    memory.register_defaults()
    predictor = ShortHorizonPredictor(pattern_memory=memory)
    bundle = predictor.forecast(_entity_with_history())
    assert bundle.matched_motif_name is not None
    assert bundle.motif_match_score >= 0.0


def test_calibrator_integration_sets_calibrated_confidence() -> None:
    calibrator = ConfidenceCalibrator()
    predictor = ShortHorizonPredictor(calibrator=calibrator)
    bundle = predictor.forecast(_entity_with_history())
    assert bundle.calibration_applied is True
    for window in bundle.windows:
        for hyp in window.hypotheses:
            assert hyp.calibrated_confidence is not None
            assert "calibrated_score" in hyp.calibrated_confidence
            assert hyp.raw_probability > 0.0


def test_full_integration_pattern_and_calibrator() -> None:
    memory = PatternMemory()
    memory.register_defaults()
    calibrator = ConfidenceCalibrator()
    predictor = ShortHorizonPredictor(pattern_memory=memory, calibrator=calibrator)
    bundle = predictor.forecast(_entity_with_history())
    assert bundle.calibration_applied is True
    assert bundle.matched_motif_name is not None
    # Tactical confidence shaping: calibrated probability should diverge from raw.
    first = bundle.windows[0].hypotheses[0]
    assert first.raw_probability != first.probability


if __name__ == "__main__":
    test_forecast_without_optional_components()
    test_window_and_hypothesis_counts()
    test_probabilities_are_bounded()
    test_trend_inference_escalating()
    test_to_dict_contains_chunk4_bundle_fields()
    test_pattern_memory_integration_sets_motif_metadata()
    test_calibrator_integration_sets_calibrated_confidence()
    test_full_integration_pattern_and_calibrator()
    print("All Short Horizon Predictor tests passed")

