"""Unit tests for interceptor pre-positioning optimizer.

Military context:
These tests verify launch-timing math used to stage interceptors ahead of
incoming threats so engagement windows are preserved.
"""

from __future__ import annotations

import math

import pytest

from services.predictive_defense.models import SwarmIntent, SwarmPrediction, ThreatTrajectoryPrediction
from services.predictive_defense.preposition_optimizer import PrePositionOptimizer


def _prediction(
    *,
    track_id: str = "trk-1",
    predicted_30s: tuple[float, float, float] | None = (100.0, 0.0, 200.0),
    predicted_60s: tuple[float, float, float] | None = (200.0, 0.0, 200.0),
    time_to_asset_s: float = 40.0,
) -> ThreatTrajectoryPrediction:
    return ThreatTrajectoryPrediction(
        track_id=track_id,
        current_position=(0.0, -500.0, 200.0),
        current_heading_deg=0.0,
        time_to_asset_s=time_to_asset_s,
        prediction_confidence=0.9,
        predicted_30s=predicted_30s,
        predicted_60s=predicted_60s,
        genome_match="sha256:abc123",
    )


def test_compute_intercept_window_prefers_60s_prediction() -> None:
    optimizer = PrePositionOptimizer(interceptor_speed_mps=100.0, interceptor_launch_delay_s=10.0)
    window = optimizer.compute_intercept_window(_prediction(), interceptor_position=(0.0, 0.0, 0.0))
    assert window.intercept_position == (200.0, 0.0, 200.0)
    assert window.window_start_s > 0.0


def test_optimize_preposition_recomputes_timing_when_falling_back_to_30s() -> None:
    optimizer = PrePositionOptimizer(
        interceptor_speed_mps=10.0,
        interceptor_launch_delay_s=5.0,
        min_engagement_window_s=2.0,
    )
    pred = _prediction(
        predicted_60s=(300.0, 0.0, 0.0),
        predicted_30s=(100.0, 0.0, 0.0),
        time_to_asset_s=20.0,
    )
    cmds = optimizer.optimize_preposition(
        [pred],
        [{"interceptor_id": "intc-1", "position": (0.0, 0.0, 0.0)}],
    )
    assert len(cmds) == 1
    cmd = cmds[0]
    assert math.isclose(cmd.time_to_station_s, 15.0, rel_tol=1e-9)
    assert math.isclose(cmd.launch_time_offset_s, 10.0, rel_tol=1e-9)
    assert cmd.engagement_window_s >= 5.0


def test_optimize_preposition_adds_swarm_context_to_reasoning() -> None:
    optimizer = PrePositionOptimizer()
    swarm = SwarmPrediction(track_count=4, intent=SwarmIntent.SATURATION, confidence=0.7)
    cmds = optimizer.optimize_preposition(
        [_prediction(track_id="trk-77")],
        [{"interceptor_id": "intc-9", "position": (0.0, 0.0, 0.0)}],
        swarm=swarm,
    )
    assert len(cmds) == 1
    assert "genome: sha256:abc123" in cmds[0].reasoning
    assert "Swarm of 4, intent: saturation" in cmds[0].reasoning


def test_optimize_preposition_rejects_invalid_interceptor_position() -> None:
    optimizer = PrePositionOptimizer()
    with pytest.raises(ValueError):
        optimizer.optimize_preposition(
            [_prediction()],
            [{"interceptor_id": "intc-bad", "position": (1.0, 2.0)}],
        )
