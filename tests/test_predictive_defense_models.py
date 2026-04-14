"""Unit tests for predictive defense data models.

Military context:
Input validation at model boundaries prevents malformed intelligence data from
producing unsafe interceptor launch recommendations.
"""

from __future__ import annotations

import pytest

from services.predictive_defense.models import (
    PrePositionCommand,
    SwarmIntent,
    SwarmPrediction,
    ThreatTrajectoryPrediction,
)


def test_threat_trajectory_prediction_normalizes_heading() -> None:
    prediction = ThreatTrajectoryPrediction(
        track_id="trk-1",
        current_position=(10.0, -5.0, 120.0),
        current_heading_deg=370.0,
        time_to_asset_s=45.0,
        prediction_confidence=0.8,
    )
    assert prediction.current_heading_deg == 10.0


def test_threat_trajectory_prediction_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        ThreatTrajectoryPrediction(
            track_id="trk-2",
            current_position=(0.0, 0.0, 0.0),
            current_heading_deg=90.0,
            time_to_asset_s=25.0,
            prediction_confidence=1.5,
        )


def test_swarm_prediction_requires_positive_track_count() -> None:
    with pytest.raises(ValueError):
        SwarmPrediction(track_count=0, intent=SwarmIntent.STRIKE)


def test_preposition_command_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError):
        PrePositionCommand(
            interceptor_id="intc-1",
            target_track_id="trk-8",
            launch_now=False,
            intercept_position=(0.0, 0.0, 100.0),
            loiter_altitude_m=100.0,
            launch_time_offset_s=5.0,
            time_to_station_s=20.0,
            engagement_window_s=15.0,
            reasoning="test",
            confidence=1.1,
        )
