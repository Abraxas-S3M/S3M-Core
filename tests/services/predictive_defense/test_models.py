"""Unit tests for predictive-defense data models.

Military context:
Model validation here blocks malformed threat-track telemetry from polluting
swarm intent estimation during active air-defense operations.
"""

from __future__ import annotations

import math

import pytest

from services.predictive_defense.models import SwarmIntent, SwarmPrediction, ThreatTrajectoryPrediction


def test_threat_trajectory_prediction_rejects_invalid_track_id() -> None:
    with pytest.raises(ValueError):
        ThreatTrajectoryPrediction(
            track_id="",
            current_position=(0.0, 0.0, 1000.0),
            current_speed_mps=30.0,
            time_to_asset_s=90.0,
        )


def test_threat_trajectory_prediction_rejects_non_finite_speed() -> None:
    with pytest.raises(ValueError):
        ThreatTrajectoryPrediction(
            track_id="trk-1",
            current_position=(0.0, 0.0, 1000.0),
            current_speed_mps=math.nan,
            time_to_asset_s=90.0,
        )


def test_swarm_prediction_rejects_out_of_bounds_pk() -> None:
    with pytest.raises(ValueError):
        SwarmPrediction(
            track_ids=["t1", "t2", "t3"],
            track_count=3,
            intent=SwarmIntent.UNKNOWN,
            convergence_point=(0.0, 0.0, 0.0),
            convergence_spread_m=100.0,
            convergence_time_s=60.0,
            approach_bearing_deg=25.0,
            average_speed_mps=35.0,
            first_arrival_s=55.0,
            last_arrival_s=65.0,
            wave_spacing_s=5.0,
            estimated_pk_defense=1.2,
            effectors_required=3,
        )
