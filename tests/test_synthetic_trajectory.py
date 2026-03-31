"""Tests for trajectory synthetic data generation."""

from __future__ import annotations

from src.simulation.synthetic.trajectory_generator import TrajectoryGenerator


def test_generate_uav_flight_returns_records():
    generator = TrajectoryGenerator()
    records = generator.generate_uav_flight(n_waypoints=5, speed=12.0, dt=0.5)
    assert len(records) > 0


def test_trajectory_within_bounds():
    bounds = ((0, 0, 0), (100, 120, 80))
    generator = TrajectoryGenerator(bounds=bounds)
    records = generator.generate_uav_flight(n_waypoints=4, speed=10.0, dt=0.5)
    for record in records:
        assert 0 <= record["x"] <= 100
        assert 0 <= record["y"] <= 120
        assert 0 <= record["z"] <= 80


def test_battery_decreases_over_time():
    generator = TrajectoryGenerator()
    records = generator.generate_uav_flight(n_waypoints=6, speed=10.0, dt=0.5)
    assert records[0]["battery_pct"] >= records[-1]["battery_pct"]


def test_generate_swarm_trajectories_agent_count():
    generator = TrajectoryGenerator()
    trajectories = generator.generate_swarm_trajectories(n_agents=5, duration=30.0)
    assert len(trajectories) == 5
    assert all(len(v) > 0 for v in trajectories.values())


def test_generate_evasive_maneuver_moves_away():
    generator = TrajectoryGenerator()
    start = (500.0, 500.0, 90.0)
    threat = (520.0, 520.0, 0.0)
    records = generator.generate_evasive_maneuver(start=start, threat_position=threat)
    first = records[0]
    last = records[-1]

    def dist(point):
        dx = point["x"] - threat[0]
        dy = point["y"] - threat[1]
        return (dx * dx + dy * dy) ** 0.5

    assert dist(last) > dist(first)
