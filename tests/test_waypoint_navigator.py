"""Unit tests for waypoint mission navigator."""

from __future__ import annotations

from datetime import datetime, timezone

from src.navigation.models import Pose, PlatformType, Waypoint
from src.navigation.planning.waypoint_navigator import WaypointNavigator


def _pose(x: float, y: float, z: float) -> Pose:
    return Pose(
        position=(x, y, z),
        orientation=(0.0, 0.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        timestamp=datetime.now(timezone.utc),
        confidence=0.9,
        source="fused",
    )


def test_load_mission_with_three_waypoints():
    nav = WaypointNavigator()
    plan_id = nav.load_mission(
        [
            Waypoint(position=(0.0, 0.0, 10.0), radius=2.0),
            Waypoint(position=(30.0, 0.0, 10.0), radius=2.0),
            Waypoint(position=(60.0, 0.0, 10.0), radius=2.0),
        ],
        platform_type=PlatformType.QUADROTOR,
    )
    assert plan_id.startswith("nav-")
    assert len(nav.paths) == 2
    assert len(nav.trajectories) == 2


def test_update_advances_to_next_waypoint():
    nav = WaypointNavigator()
    nav.load_mission(
        [
            Waypoint(position=(0.0, 0.0, 10.0), radius=2.0),
            Waypoint(position=(10.0, 0.0, 10.0), radius=2.0),
            Waypoint(position=(20.0, 0.0, 10.0), radius=2.0),
        ]
    )
    nav.start()
    update = nav.update(_pose(10.0, 0.0, 10.0))
    assert update["status"] in {"active", "completed", "loitering"}
    assert nav.current_segment_idx >= 0


def test_update_returns_target_position_velocity():
    nav = WaypointNavigator()
    nav.load_mission(
        [
            Waypoint(position=(0.0, 0.0, 10.0), radius=1.0),
            Waypoint(position=(30.0, 0.0, 10.0), radius=1.0),
        ]
    )
    nav.start()
    update = nav.update(_pose(0.0, 0.0, 10.0))
    assert "target_position" in update
    assert "target_velocity" in update
    assert isinstance(update["target_position"], tuple)
    assert isinstance(update["target_velocity"], tuple)


def test_all_waypoints_visited_completed():
    nav = WaypointNavigator()
    nav.load_mission(
        [
            Waypoint(position=(0.0, 0.0, 10.0), radius=2.0),
            Waypoint(position=(5.0, 0.0, 10.0), radius=2.0),
        ]
    )
    nav.start()
    result = nav.update(_pose(5.0, 0.0, 10.0))
    result = nav.update(_pose(5.0, 0.0, 10.0))
    assert result["status"] == "completed"


def test_replan_remaining_segments():
    nav = WaypointNavigator()
    nav.load_mission(
        [
            Waypoint(position=(0.0, 0.0, 10.0), radius=1.0),
            Waypoint(position=(20.0, 0.0, 10.0), radius=1.0),
            Waypoint(position=(40.0, 0.0, 10.0), radius=1.0),
        ]
    )
    before = len(nav.paths)
    nav.replan([{"position": (10.0, 0.0, 10.0), "radius": 3.0}])
    after = len(nav.paths)
    assert before == after == 2


def test_abort_stops_navigation():
    nav = WaypointNavigator()
    nav.load_mission(
        [
            Waypoint(position=(0.0, 0.0, 10.0), radius=1.0),
            Waypoint(position=(10.0, 0.0, 10.0), radius=1.0),
        ]
    )
    nav.start()
    nav.abort()
    assert nav.active is False
