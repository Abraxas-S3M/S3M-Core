"""Unit tests for genome-enhanced trajectory prediction.

Military context:
These checks verify that doctrine-aware biases are applied predictably, so
air-defense planners can trust timing and range estimates under threat pressure.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from services.predictive_defense.trajectory_predictor import TrajectoryPredictor
from src.prediction.prediction_models import (
    EntitySnapshot,
    ExplanationBlock,
    ForecastBundle,
    ForecastWindow,
    PredictedEntityState,
    PredictionHypothesis,
    UncertaintyEstimate,
)


@dataclass
class _StubPredictor:
    """Deterministic forecast producer for predictor unit tests."""

    confidence: float = 0.6

    def forecast(self, entity: EntitySnapshot) -> ForecastBundle:
        del entity
        windows = [
            ForecastWindow(
                horizon_s=30.0,
                hypotheses=[
                    PredictionHypothesis(
                        label="continue_course",
                        probability=0.75,
                        predicted_state=PredictedEntityState(
                            horizon_s=30.0,
                            position=(1000.0, 3000.0, 500.0),
                            speed_mps=100.0,
                            heading_deg=0.0,
                            threat_level="high",
                        ),
                        uncertainty=UncertaintyEstimate(),
                        explanation=ExplanationBlock(summary="baseline"),
                    ),
                ],
            ),
            ForecastWindow(
                horizon_s=60.0,
                hypotheses=[
                    PredictionHypothesis(
                        label="continue_course",
                        probability=0.8,
                        predicted_state=PredictedEntityState(
                            horizon_s=60.0,
                            position=(1000.0, 2000.0, 500.0),
                            speed_mps=100.0,
                            heading_deg=0.0,
                            threat_level="high",
                        ),
                        uncertainty=UncertaintyEstimate(),
                        explanation=ExplanationBlock(summary="baseline"),
                    ),
                ],
            ),
            ForecastWindow(
                horizon_s=120.0,
                hypotheses=[
                    PredictionHypothesis(
                        label="continue_course",
                        probability=0.7,
                        predicted_state=PredictedEntityState(
                            horizon_s=120.0,
                            position=(1000.0, 1000.0, 500.0),
                            speed_mps=100.0,
                            heading_deg=0.0,
                            threat_level="high",
                        ),
                        uncertainty=UncertaintyEstimate(),
                        explanation=ExplanationBlock(summary="baseline"),
                    ),
                ],
            ),
        ]
        return ForecastBundle(
            entity_id="track-1",
            windows=windows,
            forecast_confidence=self.confidence,
        )


def _entity_snapshot() -> EntitySnapshot:
    return EntitySnapshot(
        entity_id="track-1",
        entity_type="uav",
        position=(1000.0, 4000.0, 500.0),
        speed_mps=100.0,
        heading_deg=0.0,
        threat_level="high",
    )


def test_predict_without_genome_context_uses_base_confidence() -> None:
    predictor = TrajectoryPredictor(
        predictor=_StubPredictor(confidence=0.62),
        defended_position=(1000.0, 0.0, 500.0),
        outer_zone_radius_m=1500.0,
    )

    prediction = predictor.predict(_entity_snapshot(), genome_context=None)

    assert prediction.genome_bias_applied is False
    assert prediction.genome_match is None
    assert prediction.prediction_confidence == pytest.approx(0.62)
    assert prediction.range_to_asset_60s_m < prediction.range_to_asset_now_m


def test_predict_applies_genome_bias_and_blends_confidence() -> None:
    predictor = TrajectoryPredictor(
        predictor=_StubPredictor(confidence=0.6),
        defended_position=(1000.0, 0.0, 500.0),
    )
    genome_context = {
        "actor_name": "houthi-drone-doctrine",
        "confidence": 0.8,
        "behavioral_pattern": "staged loiter then dive",
        "approach_bearing": 90.0,
        "speed_range_mps": (180.0, 220.0),
    }

    prediction = predictor.predict(_entity_snapshot(), genome_context=genome_context)

    assert prediction.genome_bias_applied is True
    assert prediction.genome_match == "houthi-drone-doctrine"
    assert prediction.behavioral_pattern == "staged loiter then dive"
    assert prediction.prediction_confidence == pytest.approx(0.7)
    assert prediction.predicted_30s is not None
    assert prediction.predicted_30s != (1000.0, 3000.0, 500.0)


def test_predict_ignores_malformed_genome_values_safely() -> None:
    predictor = TrajectoryPredictor(
        predictor=_StubPredictor(confidence=0.65),
        defended_position=(1000.0, 0.0, 500.0),
    )
    malformed_context = {
        "actor_name": "unknown",
        "confidence": "bad-input",
        "approach_bearing": "not-a-bearing",
        "speed_range_mps": ["bad", "data"],
    }

    prediction = predictor.predict(_entity_snapshot(), genome_context=malformed_context)

    assert prediction.genome_match == "unknown"
    assert prediction.genome_confidence == 0.0
    assert prediction.genome_bias_applied is False
    assert prediction.prediction_confidence == pytest.approx(0.65)


def test_predictor_rejects_negative_outer_zone_radius() -> None:
    with pytest.raises(ValueError):
        TrajectoryPredictor(outer_zone_radius_m=-1.0)
