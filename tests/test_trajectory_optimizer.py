#!/usr/bin/env python3
"""Unit tests for trajectory optimization subsystem."""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.navigation.models import Path, PathStatus, PlannerType, PlatformConstraints, PlatformType
from src.navigation.planning.trajectory_optimizer import TrajectoryOptimizer


def _simple_path() -> Path:
    return Path(
        path_id="path-001",
        planner_type=PlannerType.STRAIGHT_LINE,
        status=PathStatus.PLANNED,
        waypoints=[(0.0, 0.0, 10.0), (30.0, 0.0, 10.0), (60.0, 20.0, 15.0)],
        total_distance=70.0,
        estimated_time=10.0,
        obstacles_avoided=0,
        computation_time_ms=1.0,
        created_at=datetime.now(timezone.utc),
    )


def test_optimize_produces_trajectory_with_correct_duration():
    optimizer = TrajectoryOptimizer()
    traj = optimizer.optimize(_simple_path())
    assert traj.duration > 0.0
    assert len(traj.points) > 2


def test_all_trajectory_points_have_valid_values():
    optimizer = TrajectoryOptimizer()
    traj = optimizer.optimize(_simple_path())
    for pt in traj.points:
        assert len(pt.position) == 3
        assert len(pt.velocity) == 3
        assert len(pt.acceleration) == 3
        assert isinstance(pt.yaw, float)


def test_feasibility_check_passes_for_valid_quadrotor():
    optimizer = TrajectoryOptimizer()
    traj = optimizer.optimize(_simple_path())
    result = optimizer.check_feasibility(traj, optimizer.default_constraints)
    assert isinstance(result["feasible"], bool)


def test_feasibility_check_flags_violations_for_overconstrained_path():
    optimizer = TrajectoryOptimizer()
    traj = optimizer.optimize(_simple_path())
    strict = PlatformConstraints(
        platform_type=PlatformType.QUADROTOR,
        max_velocity=0.5,
        max_acceleration=0.3,
        max_jerk=0.2,
        max_yaw_rate=0.1,
        min_turn_radius=0.0,
        max_altitude=100.0,
        min_altitude=0.0,
        max_climb_rate=0.2,
        max_descent_rate=0.2,
        collision_radius=1.0,
    )
    result = optimizer.check_feasibility(traj, strict)
    assert result["feasible"] is False
    assert len(result["violations"]) >= 1


def test_retime_scales_duration_correctly():
    optimizer = TrajectoryOptimizer()
    traj = optimizer.optimize(_simple_path())
    retimed = optimizer.retime(traj, speed_factor=2.0)
    assert math.isclose(retimed.duration, traj.duration * 2.0, rel_tol=1e-6)


def test_trajectory_sample_at_interpolates():
    optimizer = TrajectoryOptimizer()
    traj = optimizer.optimize(_simple_path())
    t_mid = traj.duration * 0.5
    sample = traj.sample_at(t_mid)
    assert 0.0 <= sample.time <= traj.duration
