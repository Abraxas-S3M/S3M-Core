"""Planning manager orchestrating tactical path and trajectory generation."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from src.navigation.models import Path, PlannerType, PlatformType, Pose, Trajectory, Waypoint
from src.navigation.planning.collision_checker import CollisionChecker
from src.navigation.planning.path_planner import PathPlanner
from src.navigation.planning.trajectory_optimizer import TrajectoryOptimizer
from src.navigation.planning.waypoint_navigator import WaypointNavigator


class PlanningManager:
    """Coordinates route planning, safety checks, and mission navigation state."""

    def __init__(self) -> None:
        self.path_planner = PathPlanner()
        self.trajectory_optimizer = TrajectoryOptimizer()
        self.collision_checker = CollisionChecker()
        self.active_plans: Dict[str, Dict[str, Any]] = {}
        self.navigators: Dict[str, WaypointNavigator] = {}

    def _parse_platform(self, platform_type: Optional[str | PlatformType]) -> PlatformType:
        if platform_type is None:
            return PlatformType.QUADROTOR
        if isinstance(platform_type, PlatformType):
            return platform_type
        return PlatformType.from_value(platform_type)

    def plan_route(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        obstacles: Optional[List[Dict[str, Any]]] = None,
        planner_type: Optional[PlannerType | str] = None,
        platform_type: Optional[PlatformType | str] = None,
    ) -> Dict[str, Any]:
        obs = obstacles or []
        planner_choice = PlannerType.from_value(planner_type) if planner_type is not None else None
        path = self.path_planner.plan(start=start, goal=goal, obstacles=obs, planner_type=planner_choice)
        collision = self.collision_checker.check_path(path, obs)
        if not collision["safe"] and planner_choice != PlannerType.RRT_STAR:
            path = self.path_planner.plan(start=start, goal=goal, obstacles=obs, planner_type=PlannerType.RRT_STAR)
            collision = self.collision_checker.check_path(path, obs)
        traj = self.trajectory_optimizer.optimize(path)
        if not collision["safe"]:
            path = self.path_planner.plan(start=start, goal=goal, obstacles=obs, planner_type=PlannerType.STRAIGHT_LINE)
            traj = self.trajectory_optimizer.optimize(path)
            collision = self.collision_checker.check_path(path, obs)
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        payload = {"path": path, "trajectory": traj, "collision_check": collision, "plan_id": plan_id}
        self.active_plans[plan_id] = payload
        _ = self._parse_platform(platform_type)
        return payload

    def plan_waypoint_mission(self, waypoints: List[Dict[str, Any]], platform_type: str = "quadrotor") -> str:
        parsed: List[Waypoint] = []
        for item in waypoints:
            pos = item.get("position")
            if not isinstance(pos, (list, tuple)) or len(pos) != 3:
                raise ValueError("Each waypoint must include a position of three values")
            parsed.append(
                Waypoint(
                    position=(float(pos[0]), float(pos[1]), float(pos[2])),
                    radius=float(item.get("radius", 2.0)),
                    speed=float(item["speed"]) if item.get("speed") is not None else None,
                    loiter_seconds=float(item.get("loiter_seconds", 0.0)),
                    heading=float(item["heading"]) if item.get("heading") is not None else None,
                )
            )
        navigator = WaypointNavigator(path_planner=self.path_planner, trajectory_optimizer=self.trajectory_optimizer)
        nav_plan_id = navigator.load_mission(parsed, platform_type=self._parse_platform(platform_type))
        navigator.start()
        self.navigators[nav_plan_id] = navigator
        first_path = navigator.paths[0] if navigator.paths else None
        self.active_plans[nav_plan_id] = {
            "plan_id": nav_plan_id,
            "path": first_path,
            "trajectory": navigator.get_trajectory(),
            "collision_check": {},
            "navigator": navigator,
        }
        return nav_plan_id

    def update_navigation(self, plan_id: str, current_pose: Pose) -> Dict[str, Any]:
        if plan_id not in self.navigators:
            raise ValueError(f"Unknown navigation plan: {plan_id}")
        return self.navigators[plan_id].update(current_pose)

    def replan(self, plan_id: str, new_obstacles: List[Dict[str, Any]]) -> None:
        if plan_id not in self.navigators:
            raise ValueError(f"Unknown navigation plan: {plan_id}")
        self.navigators[plan_id].replan(new_obstacles or [])
        self.active_plans[plan_id]["trajectory"] = self.navigators[plan_id].get_trajectory()

    def get_active_plans(self) -> List[Dict[str, Any]]:
        plans: List[Dict[str, Any]] = []
        for plan_id, plan in self.active_plans.items():
            path: Optional[Path] = plan.get("path")
            traj: Optional[Trajectory] = plan.get("trajectory")
            payload = {
                "plan_id": plan_id,
                "has_path": path is not None,
                "has_trajectory": traj is not None,
                "path_id": path.path_id if path else None,
                "trajectory_id": traj.trajectory_id if traj else None,
            }
            if "navigator" in plan:
                payload["status"] = plan["navigator"].get_status()
            plans.append(payload)
        return plans

    def health_check(self) -> Dict[str, Any]:
        return {
            "active_route_plans": len([p for p in self.active_plans.values() if p.get("path") is not None]),
            "active_navigators": len(self.navigators),
            "planner_default": self.path_planner.default_planner.value,
        }
