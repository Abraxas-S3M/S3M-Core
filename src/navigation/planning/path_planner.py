"""Path planning algorithms for tactical movement in contested environments."""

from __future__ import annotations

import logging
import math
import random
import time
import uuid
from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Dict, List, Optional, Tuple

from src.navigation.models import Path, PathStatus, PlannerType

LOGGER = logging.getLogger(__name__)

try:
    import ompl  # type: ignore  # pragma: no cover

    OMPL_AVAILABLE = True
except Exception:  # pragma: no cover
    OMPL_AVAILABLE = False


def _dist3(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _line_sphere_hit(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    center: Tuple[float, float, float],
    radius: float,
) -> bool:
    vx, vy, vz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
    wx, wy, wz = p1[0] - center[0], p1[1] - center[1], p1[2] - center[2]
    a = vx * vx + vy * vy + vz * vz
    b = 2.0 * (vx * wx + vy * wy + vz * wz)
    c = wx * wx + wy * wy + wz * wz - radius * radius
    if a <= 1e-12:
        return c <= 0.0
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return False
    sqrt_disc = math.sqrt(disc)
    t1 = (-b - sqrt_disc) / (2.0 * a)
    t2 = (-b + sqrt_disc) / (2.0 * a)
    return (0.0 <= t1 <= 1.0) or (0.0 <= t2 <= 1.0)


@dataclass
class _RRTNode:
    point: Tuple[float, float, float]
    parent: Optional[int]
    cost: float


class PathPlanner:
    """Multi-algorithm planner with robust fallbacks for air-gapped deployment."""

    def __init__(self, default_planner: PlannerType = PlannerType.RRT_STAR) -> None:
        self.default_planner = PlannerType.from_value(default_planner)

    def plan(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        obstacles: Optional[List[Dict]] = None,
        planner_type: Optional[PlannerType] = None,
        bounds: Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = None,
    ) -> Path:
        obstacles = obstacles or []
        planner = PlannerType.from_value(planner_type or self.default_planner)

        if not obstacles and planner != PlannerType.STRAIGHT_LINE:
            return self._straight_line(start=start, goal=goal, planner_type=planner)
        if planner == PlannerType.STRAIGHT_LINE:
            if obstacles and self._line_collides(start, goal, obstacles):
                return self._rrt_star(start, goal, obstacles, bounds)
            return self._straight_line(start=start, goal=goal, planner_type=planner)

        if OMPL_AVAILABLE and planner in {PlannerType.RRT_STAR}:
            try:  # pragma: no cover
                return self._rrt_star(start, goal, obstacles, bounds)
            except Exception as exc:
                LOGGER.warning("OMPL unavailable at runtime or failed; using built-in planner: %s", exc)

        if planner == PlannerType.RRT_STAR:
            return self._rrt_star(start, goal, obstacles, bounds)
        if planner == PlannerType.A_STAR:
            return self._a_star(start, goal, obstacles, bounds)
        if planner == PlannerType.POTENTIAL_FIELD:
            return self._potential_field(start, goal, obstacles)
        return self._straight_line(start=start, goal=goal, planner_type=planner)

    def _line_collides(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        obstacles: List[Dict],
    ) -> bool:
        for obs in obstacles:
            center = tuple(obs.get("position", (0.0, 0.0, 0.0)))
            radius = float(obs.get("radius", 0.0))
            if _line_sphere_hit(start, goal, center, radius):
                return True
        return False

    def _is_point_in_obstacle(self, point: Tuple[float, float, float], obstacles: List[Dict]) -> bool:
        for obs in obstacles:
            pos = tuple(obs.get("position", (0.0, 0.0, 0.0)))
            radius = float(obs.get("radius", 0.0))
            if _dist3(point, pos) <= radius:
                return True
        return False

    def _segment_is_collision_free(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
        obstacles: List[Dict],
    ) -> bool:
        for obs in obstacles:
            center = tuple(obs.get("position", (0.0, 0.0, 0.0)))
            radius = float(obs.get("radius", 0.0))
            if _line_sphere_hit(p1, p2, center, radius):
                return False
        return True

    @staticmethod
    def _compute_path_distance(points: List[Tuple[float, float, float]]) -> float:
        total = 0.0
        for i in range(len(points) - 1):
            total += _dist3(points[i], points[i + 1])
        return total

    def _smooth_path(self, points: List[Tuple[float, float, float]], obstacles: List[Dict]) -> List[Tuple[float, float, float]]:
        if len(points) <= 2:
            return points
        smoothed = [points[0]]
        i = 0
        while i < len(points) - 1:
            j = len(points) - 1
            while j > i + 1:
                if self._segment_is_collision_free(points[i], points[j], obstacles):
                    break
                j -= 1
            smoothed.append(points[j])
            i = j
        return smoothed

    def _rrt_star(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        obstacles: List[Dict],
        bounds: Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]],
        max_iterations: int = 5000,
        step_size: float = 10.0,
        neighbor_radius: float = 30.0,
    ) -> Path:
        start_ts = time.perf_counter()
        if bounds is None:
            low = (
                min(start[0], goal[0]) - 50.0,
                min(start[1], goal[1]) - 50.0,
                min(start[2], goal[2]) - 20.0,
            )
            high = (
                max(start[0], goal[0]) + 50.0,
                max(start[1], goal[1]) + 50.0,
                max(start[2], goal[2]) + 20.0,
            )
        else:
            low, high = bounds

        if self._is_point_in_obstacle(start, obstacles) or self._is_point_in_obstacle(goal, obstacles):
            return self._straight_line(start=start, goal=goal, planner_type=PlannerType.STRAIGHT_LINE, status=PathStatus.FAILED)

        tree: List[_RRTNode] = [_RRTNode(point=start, parent=None, cost=0.0)]
        goal_idx: Optional[int] = None
        goal_threshold = max(2.0, step_size)

        for _ in range(max_iterations):
            if random.random() < 0.15:
                sample = goal
            else:
                sample = (
                    random.uniform(low[0], high[0]),
                    random.uniform(low[1], high[1]),
                    random.uniform(low[2], high[2]),
                )

            nearest_idx = min(range(len(tree)), key=lambda idx: _dist3(tree[idx].point, sample))
            nearest = tree[nearest_idx]
            direction = (
                sample[0] - nearest.point[0],
                sample[1] - nearest.point[1],
                sample[2] - nearest.point[2],
            )
            length = max(1e-9, _dist3(nearest.point, sample))
            scale = min(step_size, length) / length
            new_point = (
                nearest.point[0] + direction[0] * scale,
                nearest.point[1] + direction[1] * scale,
                nearest.point[2] + direction[2] * scale,
            )
            if not self._segment_is_collision_free(nearest.point, new_point, obstacles):
                continue

            near_indices = [idx for idx, node in enumerate(tree) if _dist3(node.point, new_point) <= neighbor_radius]
            best_parent = nearest_idx
            best_cost = nearest.cost + _dist3(nearest.point, new_point)
            for idx in near_indices:
                node = tree[idx]
                if not self._segment_is_collision_free(node.point, new_point, obstacles):
                    continue
                cost = node.cost + _dist3(node.point, new_point)
                if cost < best_cost:
                    best_cost = cost
                    best_parent = idx

            tree.append(_RRTNode(point=new_point, parent=best_parent, cost=best_cost))
            new_idx = len(tree) - 1

            for idx in near_indices:
                node = tree[idx]
                new_cost = best_cost + _dist3(new_point, node.point)
                if new_cost < node.cost and self._segment_is_collision_free(new_point, node.point, obstacles):
                    tree[idx] = _RRTNode(point=node.point, parent=new_idx, cost=new_cost)

            if _dist3(new_point, goal) <= goal_threshold and self._segment_is_collision_free(new_point, goal, obstacles):
                tree.append(_RRTNode(point=goal, parent=new_idx, cost=best_cost + _dist3(new_point, goal)))
                goal_idx = len(tree) - 1
                break

        if goal_idx is None:
            return self._straight_line(start=start, goal=goal, planner_type=PlannerType.STRAIGHT_LINE, status=PathStatus.FAILED)

        rev_path = []
        cur = goal_idx
        while cur is not None:
            rev_path.append(tree[cur].point)
            cur = tree[cur].parent
        waypoints = list(reversed(rev_path))
        waypoints = self._smooth_path(waypoints, obstacles)
        distance = self._compute_path_distance(waypoints)
        compute_ms = (time.perf_counter() - start_ts) * 1000.0
        return Path(
            path_id=f"path-{uuid.uuid4().hex[:12]}",
            planner_type=PlannerType.RRT_STAR,
            status=PathStatus.PLANNED,
            waypoints=waypoints,
            total_distance=distance,
            estimated_time=distance / 8.0 if distance > 0 else 0.0,
            obstacles_avoided=len(obstacles),
            computation_time_ms=compute_ms,
            created_at=time_to_datetime(),
        )

    def _a_star(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        obstacles: List[Dict],
        bounds: Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]],
        resolution: float = 5.0,
    ) -> Path:
        start_ts = time.perf_counter()
        if resolution <= 0:
            raise ValueError("resolution must be positive")

        z_fixed = start[2]
        if bounds is None:
            min_x = min(start[0], goal[0]) - 40.0
            max_x = max(start[0], goal[0]) + 40.0
            min_y = min(start[1], goal[1]) - 40.0
            max_y = max(start[1], goal[1]) + 40.0
        else:
            low, high = bounds
            min_x, min_y = low[0], low[1]
            max_x, max_y = high[0], high[1]

        width = int(max(1, round((max_x - min_x) / resolution)))
        height = int(max(1, round((max_y - min_y) / resolution)))

        def to_cell(pt: Tuple[float, float, float]) -> Tuple[int, int]:
            cx = int(round((pt[0] - min_x) / resolution))
            cy = int(round((pt[1] - min_y) / resolution))
            return (max(0, min(width, cx)), max(0, min(height, cy)))

        def to_world(cell: Tuple[int, int]) -> Tuple[float, float, float]:
            return (
                min_x + cell[0] * resolution,
                min_y + cell[1] * resolution,
                z_fixed,
            )

        blocked = set()
        for x in range(width + 1):
            for y in range(height + 1):
                wp = to_world((x, y))
                for obs in obstacles:
                    center = tuple(obs.get("position", (0.0, 0.0, 0.0)))
                    radius = float(obs.get("radius", 0.0))
                    if _dist3((wp[0], wp[1], center[2]), (center[0], center[1], center[2])) <= radius:
                        blocked.add((x, y))
                        break

        start_cell = to_cell(start)
        goal_cell = to_cell(goal)
        if start_cell in blocked or goal_cell in blocked:
            return self._straight_line(start=start, goal=goal, planner_type=PlannerType.A_STAR, status=PathStatus.FAILED)

        neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        g_score = {start_cell: 0.0}
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        open_heap = [(0.0, start_cell)]
        visited = set()

        def heuristic(a: Tuple[int, int], b: Tuple[int, int]) -> float:
            return math.hypot(a[0] - b[0], a[1] - b[1])

        found = False
        while open_heap:
            _, current = heappop(open_heap)
            if current in visited:
                continue
            visited.add(current)
            if current == goal_cell:
                found = True
                break
            for dx, dy in neighbors:
                nxt = (current[0] + dx, current[1] + dy)
                if nxt[0] < 0 or nxt[0] > width or nxt[1] < 0 or nxt[1] > height:
                    continue
                if nxt in blocked:
                    continue
                step = math.hypot(dx, dy)
                tentative = g_score[current] + step
                if tentative < g_score.get(nxt, float("inf")):
                    came_from[nxt] = current
                    g_score[nxt] = tentative
                    heappush(open_heap, (tentative + heuristic(nxt, goal_cell), nxt))

        if not found:
            return self._straight_line(start=start, goal=goal, planner_type=PlannerType.A_STAR, status=PathStatus.FAILED)

        rev_cells = [goal_cell]
        cur = goal_cell
        while cur != start_cell:
            cur = came_from[cur]
            rev_cells.append(cur)
        waypoints = [to_world(c) for c in reversed(rev_cells)]
        if waypoints:
            waypoints[0] = start
            waypoints[-1] = goal
        distance = self._compute_path_distance(waypoints)
        compute_ms = (time.perf_counter() - start_ts) * 1000.0
        return Path(
            path_id=f"path-{uuid.uuid4().hex[:12]}",
            planner_type=PlannerType.A_STAR,
            status=PathStatus.PLANNED,
            waypoints=waypoints,
            total_distance=distance,
            estimated_time=distance / 5.0 if distance > 0 else 0.0,
            obstacles_avoided=len(obstacles),
            computation_time_ms=compute_ms,
            created_at=time_to_datetime(),
        )

    def _potential_field(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        obstacles: List[Dict],
        step_size: float = 2.0,
        max_steps: int = 5000,
        attractive_gain: float = 1.0,
        repulsive_gain: float = 100.0,
        repulsive_range: float = 50.0,
    ) -> Path:
        start_ts = time.perf_counter()
        current = start
        waypoints = [start]
        no_progress_steps = 0
        last_goal_dist = _dist3(current, goal)

        for _ in range(max_steps):
            to_goal = (goal[0] - current[0], goal[1] - current[1], goal[2] - current[2])
            goal_dist = max(1e-6, _dist3(current, goal))
            if goal_dist <= max(2.0, step_size):
                waypoints.append(goal)
                break

            fx = attractive_gain * to_goal[0]
            fy = attractive_gain * to_goal[1]
            fz = attractive_gain * to_goal[2]

            for obs in obstacles:
                center = tuple(obs.get("position", (0.0, 0.0, 0.0)))
                radius = float(obs.get("radius", 0.0))
                d = _dist3(current, center)
                clearance = d - radius
                if clearance <= 1e-3:
                    fx -= repulsive_gain * (center[0] - current[0])
                    fy -= repulsive_gain * (center[1] - current[1])
                    fz -= repulsive_gain * (center[2] - current[2])
                    continue
                if clearance < repulsive_range:
                    scale = repulsive_gain * ((1.0 / clearance) - (1.0 / repulsive_range)) / (clearance * clearance)
                    fx -= scale * (center[0] - current[0])
                    fy -= scale * (center[1] - current[1])
                    fz -= scale * (center[2] - current[2])

            norm = math.sqrt(fx * fx + fy * fy + fz * fz)
            if norm < 1e-6:
                no_progress_steps += 1
                if no_progress_steps >= 100:
                    LOGGER.info("Potential field local minima encountered; falling back to RRT*")
                    return self._rrt_star(start, goal, obstacles, None)
                continue

            nxt = (
                current[0] + (fx / norm) * step_size,
                current[1] + (fy / norm) * step_size,
                current[2] + (fz / norm) * step_size,
            )
            if not self._segment_is_collision_free(current, nxt, obstacles):
                no_progress_steps += 1
                if no_progress_steps >= 100:
                    LOGGER.info("Potential field obstacle trap; falling back to RRT*")
                    return self._rrt_star(start, goal, obstacles, None)
                continue

            waypoints.append(nxt)
            current = nxt

            if goal_dist >= last_goal_dist - 1e-3:
                no_progress_steps += 1
            else:
                no_progress_steps = 0
            last_goal_dist = goal_dist

            if no_progress_steps >= 100:
                LOGGER.info("Potential field no-progress condition; falling back to RRT*")
                return self._rrt_star(start, goal, obstacles, None)

        if waypoints[-1] != goal:
            if self._segment_is_collision_free(waypoints[-1], goal, obstacles):
                waypoints.append(goal)
            else:
                return self._rrt_star(start, goal, obstacles, None)

        waypoints = self._smooth_path(waypoints, obstacles)
        distance = self._compute_path_distance(waypoints)
        compute_ms = (time.perf_counter() - start_ts) * 1000.0
        return Path(
            path_id=f"path-{uuid.uuid4().hex[:12]}",
            planner_type=PlannerType.POTENTIAL_FIELD,
            status=PathStatus.PLANNED,
            waypoints=waypoints,
            total_distance=distance,
            estimated_time=distance / 6.0 if distance > 0 else 0.0,
            obstacles_avoided=len(obstacles),
            computation_time_ms=compute_ms,
            created_at=time_to_datetime(),
        )

    def _straight_line(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        planner_type: PlannerType = PlannerType.STRAIGHT_LINE,
        status: PathStatus = PathStatus.PLANNED,
    ) -> Path:
        start_ts = time.perf_counter()
        if planner_type != PlannerType.STRAIGHT_LINE and self._line_collides(start, goal, []):
            planner_type = PlannerType.STRAIGHT_LINE
        waypoints = [start, goal]
        distance = self._compute_path_distance(waypoints)
        return Path(
            path_id=f"path-{uuid.uuid4().hex[:12]}",
            planner_type=planner_type,
            status=status,
            waypoints=waypoints,
            total_distance=distance,
            estimated_time=distance / 10.0 if distance > 0 else 0.0,
            obstacles_avoided=0,
            computation_time_ms=(time.perf_counter() - start_ts) * 1000.0,
            created_at=time_to_datetime(),
        )


def time_to_datetime():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
