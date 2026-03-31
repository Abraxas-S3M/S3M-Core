"""Collision checking for tactical path and trajectory safety assurance."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from src.navigation.models import Path, Trajectory


def _dist3(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


class CollisionChecker:
    """Ensures autonomous routes remain safe in dense tactical environments.

    Military context:
    A single collision can trigger cascading swarm attrition. This checker
    validates static and moving-hazard separation before execution.
    """

    def __init__(self, safety_margin: float = 5.0) -> None:
        if not isinstance(safety_margin, (int, float)) or float(safety_margin) < 0:
            raise ValueError("safety_margin must be a non-negative number")
        self.safety_margin = float(safety_margin)

    @staticmethod
    def line_sphere_intersection(
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
        root = math.sqrt(disc)
        t1 = (-b - root) / (2.0 * a)
        t2 = (-b + root) / (2.0 * a)
        return (0.0 <= t1 <= 1.0) or (0.0 <= t2 <= 1.0)

    @staticmethod
    def _point_segment_distance(
        point: Tuple[float, float, float],
        a: Tuple[float, float, float],
        b: Tuple[float, float, float],
    ) -> float:
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ap = (point[0] - a[0], point[1] - a[1], point[2] - a[2])
        ab_sq = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2]
        if ab_sq <= 1e-12:
            return _dist3(point, a)
        t = (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / ab_sq
        t = max(0.0, min(1.0, t))
        proj = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
        return _dist3(point, proj)

    @staticmethod
    def _predict_track_position(track: Dict, t: float) -> Tuple[float, float, float]:
        pos = tuple(track.get("position", (0.0, 0.0, 0.0)))
        vel = tuple(track.get("velocity", (0.0, 0.0, 0.0)))
        return (pos[0] + vel[0] * t, pos[1] + vel[1] * t, pos[2] + vel[2] * t)

    def check_path(
        self,
        path: Path,
        obstacles: List[Dict],
        other_tracks: Optional[List[Dict]] = None,
    ) -> Dict[str, object]:
        collisions: List[Dict[str, object]] = []
        nearest_miss = float("inf")
        ttc: Optional[float] = None
        other_tracks = other_tracks or []
        if len(path.waypoints) < 2:
            return {"safe": False, "collisions": [], "nearest_miss_meters": 0.0, "time_to_collision_seconds": None}

        segment_speed = 10.0
        elapsed = 0.0
        for idx in range(len(path.waypoints) - 1):
            p1 = path.waypoints[idx]
            p2 = path.waypoints[idx + 1]
            seg_len = max(1e-6, _dist3(p1, p2))
            seg_time = seg_len / segment_speed
            for obs in obstacles:
                center = tuple(obs.get("position", (0.0, 0.0, 0.0)))
                radius = float(obs.get("radius", 0.0)) + self.safety_margin
                if self.line_sphere_intersection(p1, p2, center, radius):
                    collisions.append(
                        {
                            "segment_index": idx,
                            "obstacle_id": str(obs.get("id", f"obs-{idx}")),
                            "distance": 0.0,
                            "position": center,
                        }
                    )
                    if ttc is None:
                        ttc = elapsed
                miss = self._point_segment_distance(center, p1, p2) - radius
                nearest_miss = min(nearest_miss, miss)

            for track in other_tracks:
                tr_pos = self._predict_track_position(track, elapsed)
                tr_radius = float(track.get("radius", 2.0)) + self.safety_margin
                if self.line_sphere_intersection(p1, p2, tr_pos, tr_radius):
                    collisions.append(
                        {
                            "segment_index": idx,
                            "obstacle_id": str(track.get("track_id", "track")),
                            "distance": 0.0,
                            "position": tr_pos,
                        }
                    )
                    if ttc is None:
                        ttc = elapsed
                miss = self._point_segment_distance(tr_pos, p1, p2) - tr_radius
                nearest_miss = min(nearest_miss, miss)
            elapsed += seg_time

        if nearest_miss == float("inf"):
            nearest_miss = 9999.0
        return {
            "safe": len(collisions) == 0,
            "collisions": collisions,
            "nearest_miss_meters": max(0.0, nearest_miss),
            "time_to_collision_seconds": ttc,
        }

    def check_trajectory(
        self,
        trajectory: Trajectory,
        obstacles: List[Dict],
        other_tracks: Optional[List[Dict]] = None,
    ) -> Dict[str, object]:
        collisions: List[Dict[str, object]] = []
        nearest_miss = float("inf")
        ttc: Optional[float] = None
        other_tracks = other_tracks or []

        for i, point in enumerate(trajectory.points):
            for obs in obstacles:
                center = tuple(obs.get("position", (0.0, 0.0, 0.0)))
                radius = float(obs.get("radius", 0.0)) + self.safety_margin
                distance = _dist3(point.position, center)
                nearest_miss = min(nearest_miss, distance - radius)
                if distance <= radius:
                    collisions.append(
                        {
                            "segment_index": i,
                            "obstacle_id": str(obs.get("id", f"obs-{i}")),
                            "distance": max(0.0, distance - radius),
                            "position": center,
                            "time": point.time,
                        }
                    )
                    if ttc is None:
                        ttc = point.time

            for track in other_tracks:
                tr_pos = self._predict_track_position(track, point.time)
                tr_radius = float(track.get("radius", 2.0)) + self.safety_margin
                distance = _dist3(point.position, tr_pos)
                nearest_miss = min(nearest_miss, distance - tr_radius)
                if distance <= tr_radius:
                    collisions.append(
                        {
                            "segment_index": i,
                            "obstacle_id": str(track.get("track_id", "track")),
                            "distance": max(0.0, distance - tr_radius),
                            "position": tr_pos,
                            "time": point.time,
                        }
                    )
                    if ttc is None:
                        ttc = point.time
        if nearest_miss == float("inf"):
            nearest_miss = 9999.0
        return {
            "safe": len(collisions) == 0,
            "collisions": collisions,
            "nearest_miss_meters": max(0.0, nearest_miss),
            "time_to_collision_seconds": ttc,
        }

    def find_safe_corridor(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        obstacles: List[Dict],
        corridor_width: float = 20.0,
    ) -> List[Tuple[float, float, float]]:
        if corridor_width <= 0:
            raise ValueError("corridor_width must be positive")
        direct_safe = True
        for obs in obstacles:
            center = tuple(obs.get("position", (0.0, 0.0, 0.0)))
            radius = float(obs.get("radius", 0.0)) + (corridor_width * 0.5)
            if self.line_sphere_intersection(start, goal, center, radius):
                direct_safe = False
                break
        if direct_safe:
            return [start, goal]

        # Tactical detour corridor: create offset midpoint away from nearest obstacle.
        nearest = min(obstacles, key=lambda o: _dist3(tuple(o.get("position", (0.0, 0.0, 0.0))), start))
        c = tuple(nearest.get("position", (0.0, 0.0, 0.0)))
        sg = (goal[0] - start[0], goal[1] - start[1], goal[2] - start[2])
        perp = (-sg[1], sg[0], 0.0)
        norm = math.sqrt(perp[0] * perp[0] + perp[1] * perp[1] + perp[2] * perp[2])
        if norm <= 1e-9:
            perp = (0.0, 1.0, 0.0)
            norm = 1.0
        offset = corridor_width
        mid = (
            c[0] + (perp[0] / norm) * offset,
            c[1] + (perp[1] / norm) * offset,
            (start[2] + goal[2]) * 0.5,
        )
        return [start, mid, goal]
