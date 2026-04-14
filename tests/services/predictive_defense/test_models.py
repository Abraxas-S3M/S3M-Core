"""Unit tests for predictive defense trajectory models.

Military context:
Model-level validation blocks malformed track packets from corrupting tactical
trajectory decisions during live air-defense operations.
"""

from __future__ import annotations

import pytest

from services.predictive_defense.models import ThreatTrajectoryPrediction


def _valid_prediction() -> ThreatTrajectoryPrediction:
    return ThreatTrajectoryPrediction(
        track_id="trk-1",
        target_classification="uav",
        genome_match="houthi-drone-doctrine",
        genome_confidence=0.8,
        current_position=(100.0, 200.0, 300.0),
        current_velocity=(10.0, 20.0, 0.0),
        current_speed_mps=22.0,
        current_heading_deg=45.0,
        predicted_30s=(120.0, 240.0, 300.0),
        predicted_60s=(140.0, 280.0, 300.0),
        predicted_120s=(180.0, 360.0, 300.0),
        range_to_asset_now_m=5000.0,
        range_to_asset_30s_m=4500.0,
        range_to_asset_60s_m=3900.0,
        range_to_asset_120s_m=3000.0,
        time_to_zone_entry_s=100.0,
        time_to_asset_s=180.0,
        prediction_confidence=0.7,
        genome_bias_applied=True,
        behavioral_pattern="low-altitude ingress",
    )


def test_threat_trajectory_prediction_rejects_invalid_position() -> None:
    with pytest.raises(ValueError):
        ThreatTrajectoryPrediction(
            track_id="trk-1",
            target_classification="uav",
            genome_match=None,
            genome_confidence=0.8,
            current_position=(100.0, 200.0),  # type: ignore[arg-type]
            current_velocity=(10.0, 20.0, 0.0),
            current_speed_mps=22.0,
            current_heading_deg=45.0,
            predicted_30s=None,
            predicted_60s=None,
            predicted_120s=None,
            range_to_asset_now_m=5000.0,
            range_to_asset_30s_m=5000.0,
            range_to_asset_60s_m=5000.0,
            range_to_asset_120s_m=5000.0,
            time_to_zone_entry_s=100.0,
            time_to_asset_s=180.0,
            prediction_confidence=0.7,
            genome_bias_applied=False,
        )


def test_threat_trajectory_prediction_rejects_negative_range() -> None:
    with pytest.raises(ValueError):
        ThreatTrajectoryPrediction(
            track_id="trk-1",
            target_classification="uav",
            genome_match=None,
            genome_confidence=0.8,
            current_position=(100.0, 200.0, 300.0),
            current_velocity=(10.0, 20.0, 0.0),
            current_speed_mps=22.0,
            current_heading_deg=45.0,
            predicted_30s=None,
            predicted_60s=None,
            predicted_120s=None,
            range_to_asset_now_m=-1.0,
            range_to_asset_30s_m=5000.0,
            range_to_asset_60s_m=5000.0,
            range_to_asset_120s_m=5000.0,
            time_to_zone_entry_s=100.0,
            time_to_asset_s=180.0,
            prediction_confidence=0.7,
            genome_bias_applied=False,
        )


def test_threat_trajectory_prediction_normalizes_heading() -> None:
    prediction = ThreatTrajectoryPrediction(
        track_id="trk-1",
        target_classification="uav",
        genome_match="houthi-drone-doctrine",
        genome_confidence=0.8,
        current_position=(100.0, 200.0, 300.0),
        current_velocity=(10.0, 20.0, 0.0),
        current_speed_mps=22.0,
        current_heading_deg=450.0,
        predicted_30s=(120.0, 240.0, 300.0),
        predicted_60s=(140.0, 280.0, 300.0),
        predicted_120s=(180.0, 360.0, 300.0),
        range_to_asset_now_m=5000.0,
        range_to_asset_30s_m=4500.0,
        range_to_asset_60s_m=3900.0,
        range_to_asset_120s_m=3000.0,
        time_to_zone_entry_s=100.0,
        time_to_asset_s=180.0,
        prediction_confidence=0.7,
        genome_bias_applied=True,
    )
    assert prediction.current_heading_deg == 90.0


def test_threat_trajectory_prediction_clamps_confidence_fields() -> None:
    prediction = ThreatTrajectoryPrediction(
        track_id="trk-1",
        target_classification="uav",
        genome_match="houthi-drone-doctrine",
        genome_confidence=5.0,
        current_position=(100.0, 200.0, 300.0),
        current_velocity=(10.0, 20.0, 0.0),
        current_speed_mps=22.0,
        current_heading_deg=45.0,
        predicted_30s=(120.0, 240.0, 300.0),
        predicted_60s=(140.0, 280.0, 300.0),
        predicted_120s=(180.0, 360.0, 300.0),
        range_to_asset_now_m=5000.0,
        range_to_asset_30s_m=4500.0,
        range_to_asset_60s_m=3900.0,
        range_to_asset_120s_m=3000.0,
        time_to_zone_entry_s=100.0,
        time_to_asset_s=180.0,
        prediction_confidence=-3.0,
        genome_bias_applied=True,
    )
    assert prediction.genome_confidence == 1.0
    assert prediction.prediction_confidence == 0.0
