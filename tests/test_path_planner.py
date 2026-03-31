"""Tests for tactical path planning algorithms in Phase 8."""

from src.navigation.models import PlannerType
from src.navigation.planning.path_planner import PathPlanner


def _obstacles():
    return [
        {"id": "o1", "position": (35.0, 30.0, 0.0), "radius": 10.0},
        {"id": "o2", "position": (65.0, 55.0, 0.0), "radius": 12.0},
        {"id": "o3", "position": (45.0, 75.0, 0.0), "radius": 8.0},
    ]


def test_rrt_star_finds_path_around_obstacles():
    planner = PathPlanner(default_planner=PlannerType.RRT_STAR)
    path = planner.plan((0.0, 0.0, 10.0), (100.0, 100.0, 10.0), obstacles=_obstacles())
    assert path.waypoints[0] == (0.0, 0.0, 10.0)
    assert path.waypoints[-1] == (100.0, 100.0, 10.0)
    assert path.total_distance > 0.0
    assert path.computation_time_ms >= 0.0


def test_rrt_star_has_start_and_goal():
    planner = PathPlanner(default_planner=PlannerType.RRT_STAR)
    path = planner.plan((0.0, 0.0, 10.0), (80.0, 20.0, 10.0), obstacles=_obstacles())
    assert path.waypoints[0] == (0.0, 0.0, 10.0)
    assert path.waypoints[-1] == (80.0, 20.0, 10.0)


def test_a_star_plans_2d_ground_route():
    planner = PathPlanner(default_planner=PlannerType.A_STAR)
    path = planner.plan((0.0, 0.0, 0.0), (100.0, 0.0, 0.0), obstacles=_obstacles(), planner_type=PlannerType.A_STAR)
    assert len(path.waypoints) >= 2
    assert path.waypoints[0] == (0.0, 0.0, 0.0)
    assert path.waypoints[-1] == (100.0, 0.0, 0.0)


def test_a_star_avoids_blocked_cells():
    planner = PathPlanner(default_planner=PlannerType.A_STAR)
    obstacles = [{"id": "block", "position": (50.0, 0.0, 0.0), "radius": 15.0}]
    path = planner.plan((0.0, 0.0, 0.0), (100.0, 0.0, 0.0), obstacles=obstacles, planner_type=PlannerType.A_STAR)
    assert any(abs(wp[1]) > 0.1 for wp in path.waypoints[1:-1])


def test_potential_field_reaches_goal_single_obstacle():
    planner = PathPlanner(default_planner=PlannerType.POTENTIAL_FIELD)
    path = planner.plan(
        (0.0, 0.0, 5.0),
        (80.0, 0.0, 5.0),
        obstacles=[{"id": "mid", "position": (40.0, 0.0, 5.0), "radius": 10.0}],
        planner_type=PlannerType.POTENTIAL_FIELD,
    )
    assert path.waypoints[0] == (0.0, 0.0, 5.0)
    assert path.waypoints[-1] == (80.0, 0.0, 5.0)


def test_straight_line_direct_path():
    planner = PathPlanner(default_planner=PlannerType.STRAIGHT_LINE)
    path = planner.plan((0.0, 0.0, 0.0), (10.0, 10.0, 0.0), planner_type=PlannerType.STRAIGHT_LINE)
    assert path.waypoints == [(0.0, 0.0, 0.0), (10.0, 10.0, 0.0)]


def test_no_obstacles_returns_direct_path():
    planner = PathPlanner()
    path = planner.plan((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), obstacles=[])
    assert len(path.waypoints) == 2


def test_computation_time_populated():
    planner = PathPlanner()
    path = planner.plan((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), obstacles=[])
    assert path.computation_time_ms >= 0.0
