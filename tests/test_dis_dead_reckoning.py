"""Unit tests for DIS dead reckoning algorithms."""

from __future__ import annotations

from services.interop.dis.dead_reckoning import DISDeadReckoning


def test_algorithm_1_static_produces_no_position_change():
    dr = DISDeadReckoning()
    state = {
        "position": {"x": 10.0, "y": 20.0, "z": 30.0},
        "velocity": {"x": 5.0, "y": 0.0, "z": 0.0},
        "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0},
    }
    out = dr.extrapolate(state, dt_seconds=10.0, algorithm=1)
    assert out["position"] == state["position"]


def test_algorithm_2_fpw_moves_entity_along_velocity():
    dr = DISDeadReckoning()
    state = {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "velocity": {"x": 2.0, "y": -1.0, "z": 0.5},
        "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0},
    }
    out = dr.extrapolate(state, dt_seconds=5.0, algorithm=2)
    assert out["position"]["x"] == 10.0
    assert out["position"]["y"] == -5.0
    assert out["position"]["z"] == 2.5


def test_should_update_true_when_position_diverges_past_threshold():
    dr = DISDeadReckoning()
    current = {"position": {"x": 5.0, "y": 0.0, "z": 0.0}, "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0}}
    last = {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0}}
    assert dr.should_update(current, last, position_threshold_m=1.0)


def test_should_update_false_when_within_threshold():
    dr = DISDeadReckoning()
    current = {"position": {"x": 0.4, "y": 0.2, "z": 0.1}, "orientation": {"psi": 0.01, "theta": 0.0, "phi": 0.0}}
    last = {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0}}
    assert not dr.should_update(current, last, position_threshold_m=1.0, orientation_threshold_rad=0.05)
