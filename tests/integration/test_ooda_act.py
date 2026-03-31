"""
OODA ACT: Swarm commands -> path planning -> trajectory -> navigation -> position updates.
Tests the bridge between Layer 03 (autonomy) and Layer 05 (navigation).
"""

from __future__ import annotations

import pytest

from tests.integration._availability import has_module


NAV_PLANNING_AVAILABLE = has_module("src.navigation.planning")
NAV_CONTROL_AVAILABLE = has_module("src.navigation.control")
NAV_SAFETY_AVAILABLE = has_module("src.navigation.safety")
AUTONOMY_SWARM_AVAILABLE = has_module("src.autonomy.swarm")


@pytest.mark.skipif(not NAV_PLANNING_AVAILABLE, reason="Navigation planning layer not available in this repository snapshot")
def test_command_to_path() -> None:
    from src.navigation.planning.path_planner import PathPlanner

    planner = PathPlanner()
    obstacles = [
        {"position": (20, 20, 10), "radius": 8},
        {"position": (50, 50, 20), "radius": 10},
        {"position": (70, 80, 30), "radius": 6},
    ]
    path = planner.plan((0, 0, 0), (100, 100, 50), obstacles=obstacles)
    assert path is not None


@pytest.mark.skipif(not (NAV_PLANNING_AVAILABLE and NAV_CONTROL_AVAILABLE), reason="Navigation planning/control layers not available")
def test_path_to_trajectory() -> None:
    from src.navigation.control.trajectory_optimizer import TrajectoryOptimizer
    from src.navigation.planning.path_planner import PathPlanner

    path = PathPlanner().plan((0, 0, 0), (100, 100, 50), obstacles=[])
    optimizer = TrajectoryOptimizer(platform="quadrotor")
    trajectory = optimizer.optimize(path)
    assert trajectory is not None


@pytest.mark.skipif(not NAV_CONTROL_AVAILABLE, reason="Navigation control layer not available in this repository snapshot")
def test_waypoint_navigator_sequence() -> None:
    from src.navigation.control.waypoint_navigator import WaypointNavigator

    nav = WaypointNavigator()
    nav.load_waypoints([(10, 0, 0), (20, 0, 0), (30, 0, 0)])

    pos = [0.0, 0.0, 0.0]
    for _ in range(50):
        pos[0] += 1.0
        nav.update(tuple(pos))

    status = nav.status()
    assert status is not None


@pytest.mark.skipif(not NAV_SAFETY_AVAILABLE, reason="Navigation safety layer not available in this repository snapshot")
def test_collision_checker_integration() -> None:
    from src.navigation.safety.collision_checker import CollisionChecker

    checker = CollisionChecker()
    path = [(0, 0, 0), (50, 50, 20), (100, 100, 50)]
    result = checker.check_path(path, obstacles=[{"position": (50, 50, 20), "radius": 25}])
    assert result is not None


@pytest.mark.skipif(not AUTONOMY_SWARM_AVAILABLE, reason="Autonomy swarm layer not available in this repository snapshot")
def test_navigation_feeds_back_to_swarm() -> None:
    from src.autonomy.swarm.coordinator import SwarmCoordinator

    coordinator = SwarmCoordinator()
    coordinator.register_agent("drone_1", position=(0, 0, 50))
    coordinator.update_agent_position("drone_1", (50, 50, 50))

    state = coordinator.get_agent("drone_1")
    assert state is not None
