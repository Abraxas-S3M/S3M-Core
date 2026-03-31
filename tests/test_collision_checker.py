"""Unit tests for collision checking and safe corridor logic."""

from src.navigation.models import (
    Path,
    PathStatus,
    PlannerType,
    PlatformType,
    Trajectory,
    TrajectoryPoint,
)
from src.navigation.planning.collision_checker import CollisionChecker


def _simple_path():
    return Path(
        path_id="p1",
        planner_type=PlannerType.STRAIGHT_LINE,
        status=PathStatus.PLANNED,
        waypoints=[(0.0, 0.0, 10.0), (100.0, 0.0, 10.0)],
        total_distance=100.0,
        estimated_time=10.0,
        obstacles_avoided=0,
        computation_time_ms=1.0,
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )


def _simple_traj():
    points = [
        TrajectoryPoint(
            time=0.0,
            position=(0.0, 0.0, 10.0),
            velocity=(5.0, 0.0, 0.0),
            acceleration=(0.0, 0.0, 0.0),
            yaw=0.0,
            yaw_rate=0.0,
        ),
        TrajectoryPoint(
            time=10.0,
            position=(100.0, 0.0, 10.0),
            velocity=(0.0, 0.0, 0.0),
            acceleration=(0.0, 0.0, 0.0),
            yaw=0.0,
            yaw_rate=0.0,
        ),
    ]
    return Trajectory(
        trajectory_id="t1",
        path_id="p1",
        points=points,
        platform_type=PlatformType.QUADROTOR,
        duration=10.0,
        max_velocity=5.0,
        max_acceleration=0.0,
        feasible=True,
    )


def test_safe_path_no_obstacles():
    checker = CollisionChecker()
    result = checker.check_path(_simple_path(), [])
    assert result["safe"] is True


def test_path_through_obstacle_not_safe():
    checker = CollisionChecker(safety_margin=0.0)
    path = _simple_path()
    result = checker.check_path(path, [{"id": "obs-1", "position": (50.0, 0.0, 10.0), "radius": 10.0}])
    assert result["safe"] is False
    assert result["collisions"]


def test_nearest_miss_computation():
    checker = CollisionChecker(safety_margin=0.0)
    path = _simple_path()
    result = checker.check_path(path, [{"id": "obs-2", "position": (50.0, 20.0, 10.0), "radius": 5.0}])
    assert result["nearest_miss_meters"] >= 0.0


def test_line_sphere_intersection_geometry():
    checker = CollisionChecker()
    assert checker.line_sphere_intersection((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (5.0, 0.0, 0.0), 1.0)
    assert not checker.line_sphere_intersection((0.0, 10.0, 0.0), (10.0, 10.0, 0.0), (5.0, 0.0, 0.0), 1.0)


def test_find_safe_corridor_returns_waypoints():
    checker = CollisionChecker()
    corridor = checker.find_safe_corridor(
        start=(0.0, 0.0, 10.0),
        goal=(100.0, 0.0, 10.0),
        obstacles=[{"position": (50.0, 0.0, 10.0), "radius": 15.0}],
        corridor_width=20.0,
    )
    assert len(corridor) >= 2
