"""Unit tests for predictive-defense swarm analyzer.

Military context:
These checks verify that coordinated inbound tracks are recognized as an
attack wave and that malformed inputs are rejected before C2 decisions.
"""

from __future__ import annotations

import pytest

from services.predictive_defense.models import SwarmIntent, ThreatTrajectoryPrediction
from services.predictive_defense.swarm_analyzer import SwarmAnalyzer


def _prediction(
    track_id: str,
    x: float,
    y: float,
    speed: float = 40.0,
    time_to_asset_s: float = 120.0,
) -> ThreatTrajectoryPrediction:
    return ThreatTrajectoryPrediction(
        track_id=track_id,
        current_position=(x, y, 1000.0),
        current_speed_mps=speed,
        time_to_asset_s=time_to_asset_s,
        predicted_60s=(x * 0.3, y * 0.3, 1000.0),
        genome_match={"family": "shahed-like", "score": 0.7},
    )


def test_analyze_returns_none_when_swarm_size_is_below_threshold() -> None:
    analyzer = SwarmAnalyzer(min_swarm_size=3)
    result = analyzer.analyze([
        _prediction("t-1", 20.0, -1200.0),
        _prediction("t-2", -30.0, -1300.0),
    ])
    assert result is None


def test_analyze_detects_clustered_swarm_and_builds_prediction() -> None:
    analyzer = SwarmAnalyzer(min_swarm_size=3)
    result = analyzer.analyze([
        _prediction("t-1", 10.0, -1300.0, time_to_asset_s=80.0),
        _prediction("t-2", -20.0, -1250.0, time_to_asset_s=90.0),
        _prediction("t-3", 35.0, -1350.0, time_to_asset_s=100.0),
    ])

    assert result is not None
    assert result.track_count == 3
    assert result.intent == SwarmIntent.UNKNOWN
    assert result.approach_bearing_deg >= 0.0
    assert result.approach_bearing_deg < 360.0
    assert result.first_arrival_s == pytest.approx(80.0)
    assert result.last_arrival_s == pytest.approx(100.0)
    assert 0.0 <= result.estimated_pk_defense <= 1.0


def test_analyze_classifies_saturation_for_large_tight_group() -> None:
    analyzer = SwarmAnalyzer(min_swarm_size=3)
    predictions = [
        _prediction(f"t-{idx}", float(idx * 5 - 20), -1500.0 - idx * 20.0, time_to_asset_s=70.0 + idx)
        for idx in range(8)
    ]
    result = analyzer.analyze(predictions)
    assert result is not None
    assert result.intent == SwarmIntent.SATURATION


def test_analyze_classifies_sequential_when_arrivals_are_staggered() -> None:
    analyzer = SwarmAnalyzer(min_swarm_size=3)
    result = analyzer.analyze([
        _prediction("t-1", 0.0, -1500.0, time_to_asset_s=60.0),
        _prediction("t-2", 15.0, -1450.0, time_to_asset_s=100.0),
        _prediction("t-3", -10.0, -1520.0, time_to_asset_s=140.0),
        _prediction("t-4", 8.0, -1495.0, time_to_asset_s=180.0),
        _prediction("t-5", -5.0, -1510.0, time_to_asset_s=220.0),
    ])
    assert result is not None
    assert result.intent == SwarmIntent.SEQUENTIAL


def test_analyze_returns_none_for_non_clustered_bearings() -> None:
    analyzer = SwarmAnalyzer(min_swarm_size=3)
    result = analyzer.analyze([
        _prediction("t-1", 0.0, -1200.0),
        _prediction("t-2", 1200.0, 0.0),
        _prediction("t-3", -1200.0, 0.0),
    ])
    assert result is None


def test_analyze_rejects_malformed_defended_position() -> None:
    analyzer = SwarmAnalyzer()
    with pytest.raises(ValueError):
        analyzer.analyze(
            [_prediction("t-1", 0.0, -1200.0), _prediction("t-2", 10.0, -1210.0), _prediction("t-3", -10.0, -1190.0)],
            defended_position=(0.0, 0.0),  # type: ignore[arg-type]
        )
