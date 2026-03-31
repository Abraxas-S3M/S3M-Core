"""Waypoint mission navigator for autonomous tactical route execution."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.navigation.models import (
    Path,
    PlatformConstraints,
    PlatformType,
    Pose,
    Trajectory,
    Waypoint,
)
from src.navigation.planning.path_planner import PathPlanner
from src.navigation.planning.trajectory_optimizer import TrajectoryOptimizer


def _default_constraints(platform_type: PlatformType) -> PlatformConstraints:
    if platform_type == PlatformType.GROUND_WHEELED:
        return PlatformConstraints(
            platform_type=platform_type,
            max_velocity=8.0,
            max_acceleration=2.0,
            max_jerk=10.0,
            max_yaw_rate=1.57,
            min_turn_radius=3.0,
            max_altitude=0.0,
            min_altitude=0.0,
            max_climb_rate=0.0,
            max_descent_rate=0.0,
            collision_radius=2.0,
        )
    if platform_type == PlatformType.FIXED_WING:
        return PlatformConstraints(
            platform_type=platform_type,
            max_velocity=40.0,
            max_acceleration=3.0,
            max_jerk=15.0,
            max_yaw_rate=0.52,
            min_turn_radius=50.0,
            max_altitude=3000.0,
            min_altitude=30.0,
            max_climb_rate=8.0,
            max_descent_rate=5.0,
            collision_radius=5.0,
        )
    return PlatformConstraints(
        platform_type=platform_type,
        max_velocity=15.0,
        max_acceleration=5.0,
        max_jerk=20.0,
        max_yaw_rate=3.14,
        min_turn_radius=0.0,
        max_altitude=500.0,
        min_altitude=5.0,
        max_climb_rate=5.0,
        max_descent_rate=3.0,
        collision_radius=1.5,
    )


class WaypointNavigator:
    """Executes multi-waypoint mission segments under tactical constraints."""

    def __init__(
        self,
        path_planner: Optional[PathPlanner] = None,
        trajectory_optimizer: Optional[TrajectoryOptimizer] = None,
    ) -> None:
        self.path_planner = path_planner or PathPlanner()
        self.trajectory_optimizer = trajectory_optimizer or TrajectoryOptimizer()
        self.nav_plan_id: Optional[str] = None
        self.platform_type = PlatformType.QUADROTOR
        self.constraints = _default_constraints(self.platform_type)
        self.waypoints: List[Waypoint] = []
        self.paths: List[Path] = []
        self.trajectories: List[Trajectory] = []
        self.current_segment_idx = 0
        self.active = False
        self.completed = False
        self.segment_start_time: Optional[float] = None
        self.segment_loiter_until: Optional[float] = None
        self.segment_elapsed: float = 0.0
        self.total_distance = 0.0
        self.total_estimated_time = 0.0

    def load_mission(self, waypoints: List[Waypoint], platform_type: PlatformType = PlatformType.QUADROTOR) -> str:
        if not isinstance(waypoints, list) or len(waypoints) < 2:
            raise ValueError("waypoints must be a list of at least two Waypoint objects")
        for wp in waypoints:
            if not isinstance(wp, Waypoint):
                raise ValueError("waypoints must contain Waypoint objects")
        self.platform_type = PlatformType.from_value(platform_type)
        self.constraints = _default_constraints(self.platform_type)
        self.waypoints = waypoints
        self.paths = []
        self.trajectories = []
        self.current_segment_idx = 0
        self.completed = False
        self.active = False
        self.segment_start_time = None
        self.segment_loiter_until = None
        self.segment_elapsed = 0.0
        self.total_distance = 0.0
        self.total_estimated_time = 0.0

        for idx in range(len(waypoints) - 1):
            segment_path = self.path_planner.plan(
                start=waypoints[idx].position,
                goal=waypoints[idx + 1].position,
                obstacles=[],
            )
            self.paths.append(segment_path)
            self.total_distance += segment_path.total_distance
            self.total_estimated_time += segment_path.estimated_time
            segment_trajectory = self.trajectory_optimizer.optimize(segment_path, self.constraints)
            self.trajectories.append(segment_trajectory)

        self.nav_plan_id = f"nav-{uuid.uuid4().hex[:12]}"
        return self.nav_plan_id

    def start(self) -> bool:
        if self.nav_plan_id is None or not self.trajectories:
            return False
        self.active = True
        self.completed = False
        self.segment_start_time = time.perf_counter()
        self.segment_elapsed = 0.0
        return True

    def _current_trajectory(self) -> Optional[Trajectory]:
        if 0 <= self.current_segment_idx < len(self.trajectories):
            return self.trajectories[self.current_segment_idx]
        return None

    def update(self, current_pose: Pose) -> Dict[str, object]:
        if not isinstance(current_pose, Pose):
            raise ValueError("current_pose must be a Pose")
        if self.completed:
            return {
                "target_position": current_pose.position,
                "target_velocity": (0.0, 0.0, 0.0),
                "target_yaw": current_pose.orientation[2],
                "waypoint_index": len(self.waypoints) - 1 if self.waypoints else 0,
                "segment_progress": 1.0,
                "status": "completed",
            }
        if not self.active:
            return {
                "target_position": current_pose.position,
                "target_velocity": (0.0, 0.0, 0.0),
                "target_yaw": current_pose.orientation[2],
                "waypoint_index": self.current_segment_idx,
                "segment_progress": 0.0,
                "status": "idle",
            }
        if self.current_segment_idx >= len(self.trajectories):
            self.completed = True
            self.active = False
            return {
                "target_position": current_pose.position,
                "target_velocity": (0.0, 0.0, 0.0),
                "target_yaw": current_pose.orientation[2],
                "waypoint_index": len(self.waypoints) - 1,
                "segment_progress": 1.0,
                "status": "completed",
            }

        target_waypoint = self.waypoints[self.current_segment_idx + 1]
        now = time.perf_counter()
        if target_waypoint.is_reached(current_pose.position):
            if target_waypoint.loiter_seconds > 0.0:
                if self.segment_loiter_until is None:
                    self.segment_loiter_until = now + target_waypoint.loiter_seconds
                    return {
                        "target_position": target_waypoint.position,
                        "target_velocity": (0.0, 0.0, 0.0),
                        "target_yaw": current_pose.orientation[2],
                        "waypoint_index": self.current_segment_idx + 1,
                        "segment_progress": 1.0,
                        "status": "loitering",
                    }
                if now < self.segment_loiter_until:
                    return {
                        "target_position": target_waypoint.position,
                        "target_velocity": (0.0, 0.0, 0.0),
                        "target_yaw": current_pose.orientation[2],
                        "waypoint_index": self.current_segment_idx + 1,
                        "segment_progress": 1.0,
                        "status": "loitering",
                    }
            self.current_segment_idx += 1
            self.segment_start_time = now
            self.segment_elapsed = 0.0
            self.segment_loiter_until = None
            if self.current_segment_idx >= len(self.trajectories):
                self.completed = True
                self.active = False
                return {
                    "target_position": target_waypoint.position,
                    "target_velocity": (0.0, 0.0, 0.0),
                    "target_yaw": current_pose.orientation[2],
                    "waypoint_index": len(self.waypoints) - 1,
                    "segment_progress": 1.0,
                    "status": "completed",
                }

        traj = self._current_trajectory()
        if traj is None:
            self.completed = True
            self.active = False
            return {
                "target_position": current_pose.position,
                "target_velocity": (0.0, 0.0, 0.0),
                "target_yaw": current_pose.orientation[2],
                "waypoint_index": self.current_segment_idx,
                "segment_progress": 1.0,
                "status": "completed",
            }

        if self.segment_start_time is None:
            self.segment_start_time = now
        self.segment_elapsed = max(0.0, now - self.segment_start_time)
        sample = traj.sample_at(self.segment_elapsed)
        progress = 1.0 if traj.duration <= 0.0 else min(1.0, self.segment_elapsed / traj.duration)
        return {
            "target_position": sample.position,
            "target_velocity": sample.velocity,
            "target_yaw": sample.yaw,
            "waypoint_index": self.current_segment_idx,
            "segment_progress": progress,
            "status": "active",
        }

    def replan(self, new_obstacles: Optional[List[Dict]] = None) -> None:
        if not self.waypoints:
            raise ValueError("No mission loaded")
        obstacles = new_obstacles or []
        start_idx = self.current_segment_idx
        self.paths = self.paths[:start_idx]
        self.trajectories = self.trajectories[:start_idx]
        for idx in range(start_idx, len(self.waypoints) - 1):
            path = self.path_planner.plan(
                start=self.waypoints[idx].position,
                goal=self.waypoints[idx + 1].position,
                obstacles=obstacles,
            )
            self.paths.append(path)
            self.trajectories.append(self.trajectory_optimizer.optimize(path, self.constraints))
        self.segment_start_time = time.perf_counter()
        self.segment_elapsed = 0.0

    def get_status(self) -> Dict[str, object]:
        remaining_distance = 0.0
        remaining_time = 0.0
        for idx in range(self.current_segment_idx, len(self.paths)):
            remaining_distance += self.paths[idx].total_distance
            remaining_time += self.paths[idx].estimated_time
        return {
            "nav_plan_id": self.nav_plan_id,
            "active": self.active,
            "completed": self.completed,
            "current_waypoint_index": self.current_segment_idx,
            "total_waypoints": len(self.waypoints),
            "remaining_distance": remaining_distance,
            "estimated_time_remaining": remaining_time,
            "total_distance": self.total_distance,
            "total_estimated_time": self.total_estimated_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_trajectory(self) -> Optional[Trajectory]:
        return self._current_trajectory()

    def abort(self) -> None:
        self.active = False
        self.completed = False
