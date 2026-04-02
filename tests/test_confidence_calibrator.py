"""Tests for Chunk 4: Confidence Calibrator.

Proves:
  1. Sparse data lowers calibrated confidence vs rich data
  2. Observation disagreement lowers confidence
  3. Strong pattern match increases confidence
  4. Longer horizons penalise confidence
  5. Historical accuracy affects calibration
  6. Rationale summary is always present
  7. Confidence band widens with uncertainty
"""

import sys

sys.path.insert(0, ".")

from src.prediction.confidence_calibrator import ConfidenceCalibrator


def test_sparse_vs_rich_data() -> None:
    cal = ConfidenceCalibrator()

    sparse = cal.calibrate(
        raw_score=0.6,
        entity_confidence=0.7,
        history_depth=1,  # very sparse
        horizon_s=60.0,
    )
    rich = cal.calibrate(
        raw_score=0.6,
        entity_confidence=0.7,
        history_depth=15,  # very rich
        horizon_s=60.0,
    )

    assert rich.calibrated_score > sparse.calibrated_score
    assert rich.data_richness_factor > sparse.data_richness_factor
    assert sparse.data_richness_factor < 0.5
    assert rich.data_richness_factor >= 0.9
    assert "sparse" in " ".join(sparse.rationale).lower() or "limit" in " ".join(sparse.rationale).lower()


def test_disagreement_lowers_confidence() -> None:
    cal = ConfidenceCalibrator()

    agree = cal.calibrate(
        raw_score=0.6,
        entity_confidence=0.7,
        history_depth=8,
        heading_variance=10.0,
        speed_variance=5.0,
        threat_level_changes=0,
        horizon_s=60.0,
    )
    disagree = cal.calibrate(
        raw_score=0.6,
        entity_confidence=0.7,
        history_depth=8,
        heading_variance=600.0,
        speed_variance=200.0,
        threat_level_changes=4,
        horizon_s=60.0,
    )

    assert agree.calibrated_score > disagree.calibrated_score
    assert agree.observation_agreement_factor > disagree.observation_agreement_factor
    assert disagree.observation_agreement_factor < 0.7
    assert "disagree" in " ".join(disagree.rationale).lower()


def test_pattern_match_boosts_confidence() -> None:
    cal = ConfidenceCalibrator()
    no_pattern = cal.calibrate(raw_score=0.5, entity_confidence=0.7, history_depth=6, pattern_match_score=0.0, horizon_s=60.0)
    strong_pattern = cal.calibrate(
        raw_score=0.5,
        entity_confidence=0.7,
        history_depth=6,
        pattern_match_score=0.85,
        horizon_s=60.0,
    )
    assert strong_pattern.calibrated_score > no_pattern.calibrated_score
    assert strong_pattern.pattern_match_factor > no_pattern.pattern_match_factor
    assert "pattern" in " ".join(strong_pattern.rationale).lower()


def test_horizon_penalty() -> None:
    cal = ConfidenceCalibrator()
    short = cal.calibrate(raw_score=0.6, history_depth=8, horizon_s=30.0)
    medium = cal.calibrate(raw_score=0.6, history_depth=8, horizon_s=120.0)
    long_ = cal.calibrate(raw_score=0.6, history_depth=8, horizon_s=600.0)

    assert short.calibrated_score > medium.calibrated_score
    assert medium.calibrated_score > long_.calibrated_score
    assert short.horizon_penalty_factor > medium.horizon_penalty_factor
    assert medium.horizon_penalty_factor > long_.horizon_penalty_factor
    assert "horizon" in " ".join(long_.rationale).lower()


def test_historical_accuracy() -> None:
    cal = ConfidenceCalibrator()
    neutral = cal.calibrate(raw_score=0.6, history_depth=8, horizon_s=60.0)
    assert abs(neutral.historical_accuracy_factor - 0.5) < 0.01

    for _ in range(8):
        cal.record_outcome("continue_course", "continue_course", 60.0)
    for _ in range(2):
        cal.record_outcome("continue_course", "stop", 60.0)

    good_accuracy = cal.calibrate(raw_score=0.6, history_depth=8, horizon_s=60.0)
    assert good_accuracy.historical_accuracy_factor > 0.7
    stats = cal.get_accuracy_stats()
    assert stats["samples"] == 10
    assert abs(stats["accuracy"] - 0.8) < 0.01

    cal2 = ConfidenceCalibrator()
    for _ in range(8):
        cal2.record_outcome("continue_course", "stop", 60.0)
    for _ in range(2):
        cal2.record_outcome("continue_course", "continue_course", 60.0)
    poor_accuracy = cal2.calibrate(raw_score=0.6, history_depth=8, horizon_s=60.0)
    assert poor_accuracy.historical_accuracy_factor < 0.3
    assert good_accuracy.calibrated_score > poor_accuracy.calibrated_score


def test_rationale_present() -> None:
    cal = ConfidenceCalibrator()
    result = cal.calibrate(
        raw_score=0.5,
        entity_confidence=0.6,
        history_depth=5,
        heading_variance=50.0,
        speed_variance=20.0,
        pattern_match_score=0.4,
        horizon_s=120.0,
        source_reliability=0.7,
    )
    assert isinstance(result.rationale, list)
    assert len(result.rationale) >= 2
    d = result.to_dict()
    assert "raw_score" in d
    assert "calibrated_score" in d
    assert "confidence_band" in d and isinstance(d["confidence_band"], list) and len(d["confidence_band"]) == 2
    assert "factors" in d
    assert "rationale" in d
    assert result.calibrated_score != result.raw_score


def test_confidence_band_widens() -> None:
    cal = ConfidenceCalibrator()
    certain = cal.calibrate(
        raw_score=0.6,
        history_depth=12,
        heading_variance=5.0,
        speed_variance=2.0,
        horizon_s=30.0,
    )
    uncertain = cal.calibrate(
        raw_score=0.6,
        history_depth=1,
        heading_variance=800.0,
        speed_variance=300.0,
        threat_level_changes=5,
        horizon_s=600.0,
    )
    certain_width = certain.confidence_high - certain.confidence_low
    uncertain_width = uncertain.confidence_high - uncertain.confidence_low
    assert uncertain_width > certain_width
    assert certain.confidence_low <= certain.calibrated_score <= certain.confidence_high
    assert uncertain.confidence_low <= uncertain.calibrated_score <= uncertain.confidence_high


if __name__ == "__main__":
    test_sparse_vs_rich_data()
    test_disagreement_lowers_confidence()
    test_pattern_match_boosts_confidence()
    test_horizon_penalty()
    test_historical_accuracy()
    test_rationale_present()
    test_confidence_band_widens()
    print("All Confidence Calibrator tests passed")
