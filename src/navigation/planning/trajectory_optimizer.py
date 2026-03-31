"""Trajectory optimizer for dynamically feasible tactical motion profiles."""

from __future__ import annotations

import logging
import math
import uuid
from typing import Dict, List, Optional, Tuple

from src.navigation.models import (
    Path,
    PlatformConstraints,
    PlatformType,
    Trajectory,
    TrajectoryPoint,
)

LOGGER = logging.getLogger(__name__)

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore


class TrajectoryOptimizer:
    """Builds minimum-snap-style trajectories with robust fallback methods.

    Military context:
    The trajectory profile is used directly by flight controllers; dynamic
    feasibility is mission-critical to prevent stalls, collisions, or overshoot
    during evasive or low-altitude tactical maneuvering.
    """

    def __init__(self, platform_constraints: Optional[PlatformConstraints] = None, dt: float = 0.05) -> None:
        if not isinstance(dt, (int, float)) or float(dt) <= 0:
            raise ValueError("dt must be a positive number")
        self.dt = float(dt)
        self.default_constraints = platform_constraints or PlatformConstraints(
            platform_type=PlatformType.QUADROTOR,
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

    @staticmethod
    def _dist(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        dz = a[2] - b[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def _direction(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
        d = TrajectoryOptimizer._dist(a, b)
        if d <= 1e-9:
            return (0.0, 0.0, 0.0)
        return ((b[0] - a[0]) / d, (b[1] - a[1]) / d, (b[2] - a[2]) / d)

    def _waypoint_velocities(
        self,
        points: List[Tuple[float, float, float]],
        segment_times: List[float],
        max_velocity: float,
    ) -> List[Tuple[float, float, float]]:
        velocities: List[Tuple[float, float, float]] = []
        for i in range(len(points)):
            if i == 0 or i == len(points) - 1:
                velocities.append((0.0, 0.0, 0.0))
                continue
            prev_dir = self._direction(points[i - 1], points[i])
            next_dir = self._direction(points[i], points[i + 1])
            blend = (
                prev_dir[0] + next_dir[0],
                prev_dir[1] + next_dir[1],
                prev_dir[2] + next_dir[2],
            )
            norm = math.sqrt(blend[0] * blend[0] + blend[1] * blend[1] + blend[2] * blend[2])
            if norm <= 1e-9:
                velocities.append((0.0, 0.0, 0.0))
                continue
            avg_time = max(1e-3, 0.5 * (segment_times[i - 1] + segment_times[i]))
            span = 0.5 * (self._dist(points[i - 1], points[i]) + self._dist(points[i], points[i + 1]))
            target_speed = min(max_velocity, span / avg_time)
            velocities.append((blend[0] * target_speed / norm, blend[1] * target_speed / norm, blend[2] * target_speed / norm))
        return velocities

    def _solve_poly_segment(
        self,
        p0: float,
        p1: float,
        v0: float,
        v1: float,
        T: float,
    ) -> List[float]:
        # 7th degree polynomial with boundary conditions on p, v, a, j.
        c0 = p0
        c1 = v0
        c2 = 0.0  # a(0)=0
        c3 = 0.0  # j(0)=0
        if np is None:
            # Fallback: degenerate polynomial solved by blend curve.
            return [c0, c1, c2, c3, 0.0, 0.0, 0.0, 0.0]
        A = np.asarray(
            [
                [T**4, T**5, T**6, T**7],
                [4 * T**3, 5 * T**4, 6 * T**5, 7 * T**6],
                [12 * T**2, 20 * T**3, 30 * T**4, 42 * T**5],
                [24 * T, 60 * T**2, 120 * T**3, 210 * T**4],
            ],
            dtype=float,
        )
        b = np.asarray(
            [
                p1 - (c0 + c1 * T + c2 * T**2 + c3 * T**3),
                v1 - (c1 + 2 * c2 * T + 3 * c3 * T**2),
                0.0 - (2 * c2 + 6 * c3 * T),
                0.0 - (6 * c3),
            ],
            dtype=float,
        )
        try:
            c4, c5, c6, c7 = np.linalg.solve(A, b)
            return [c0, c1, c2, c3, float(c4), float(c5), float(c6), float(c7)]
        except Exception:
            return [c0, c1, c2, c3, 0.0, 0.0, 0.0, 0.0]

    @staticmethod
    def _poly_eval(coeffs: List[float], t: float) -> Tuple[float, float, float, float]:
        c = coeffs
        p = c[0] + c[1] * t + c[2] * t**2 + c[3] * t**3 + c[4] * t**4 + c[5] * t**5 + c[6] * t**6 + c[7] * t**7
        v = c[1] + 2 * c[2] * t + 3 * c[3] * t**2 + 4 * c[4] * t**3 + 5 * c[5] * t**4 + 6 * c[6] * t**5 + 7 * c[7] * t**6
        a = 2 * c[2] + 6 * c[3] * t + 12 * c[4] * t**2 + 20 * c[5] * t**3 + 30 * c[6] * t**4 + 42 * c[7] * t**5
        j = 6 * c[3] + 24 * c[4] * t + 60 * c[5] * t**2 + 120 * c[6] * t**3 + 210 * c[7] * t**4
        return (p, v, a, j)

    def _fallback_linear_profile(self, path: Path, constraints: PlatformConstraints) -> Trajectory:
        waypoints = path.waypoints
        points: List[TrajectoryPoint] = []
        t_cursor = 0.0
        for i in range(len(waypoints) - 1):
            p0 = waypoints[i]
            p1 = waypoints[i + 1]
            seg_dist = max(1e-9, self._dist(p0, p1))
            speed = max(0.2, min(constraints.max_velocity, seg_dist))
            seg_time = max(self.dt, seg_dist / speed)
            steps = max(2, int(math.ceil(seg_time / self.dt)))
            for k in range(steps):
                alpha = k / float(steps)
                pos = (
                    p0[0] + (p1[0] - p0[0]) * alpha,
                    p0[1] + (p1[1] - p0[1]) * alpha,
                    p0[2] + (p1[2] - p0[2]) * alpha,
                )
                vel = (
                    (p1[0] - p0[0]) / seg_time,
                    (p1[1] - p0[1]) / seg_time,
                    (p1[2] - p0[2]) / seg_time,
                )
                yaw = math.atan2(vel[1], vel[0]) if abs(vel[0]) + abs(vel[1]) > 1e-6 else 0.0
                points.append(
                    TrajectoryPoint(
                        time=t_cursor + alpha * seg_time,
                        position=pos,
                        velocity=vel,
                        acceleration=(0.0, 0.0, 0.0),
                        yaw=yaw,
                        yaw_rate=0.0,
                    )
                )
            t_cursor += seg_time
        points.append(
            TrajectoryPoint(
                time=t_cursor,
                position=waypoints[-1],
                velocity=(0.0, 0.0, 0.0),
                acceleration=(0.0, 0.0, 0.0),
                yaw=points[-1].yaw if points else 0.0,
                yaw_rate=0.0,
            )
        )
        max_vel = max(math.sqrt(p.velocity[0] ** 2 + p.velocity[1] ** 2 + p.velocity[2] ** 2) for p in points)
        return Trajectory(
            trajectory_id=f"traj-{uuid.uuid4().hex[:12]}",
            path_id=path.path_id,
            points=points,
            platform_type=constraints.platform_type,
            duration=t_cursor,
            max_velocity=max_vel,
            max_acceleration=0.0,
            feasible=max_vel <= constraints.max_velocity + 1e-6,
        )

    def optimize(self, path: Path, platform_constraints: Optional[PlatformConstraints] = None) -> Trajectory:
        constraints = platform_constraints or self.default_constraints
        if not isinstance(path, Path):
            raise ValueError("path must be a Path")
        if len(path.waypoints) < 2:
            raise ValueError("path must contain at least two waypoints")
        if np is None:
            LOGGER.warning("NumPy unavailable; trajectory optimizer using linear fallback profile")
            return self._fallback_linear_profile(path, constraints)

        time_scale = 1.0
        max_retries = 5
        last_trajectory: Optional[Trajectory] = None
        for _ in range(max_retries):
            segment_times = []
            for i in range(len(path.waypoints) - 1):
                dist = self._dist(path.waypoints[i], path.waypoints[i + 1])
                base = max(self.dt, dist / max(constraints.max_velocity, 0.5))
                segment_times.append(base * time_scale)

            waypoint_vels = self._waypoint_velocities(path.waypoints, segment_times, constraints.max_velocity)
            all_points: List[TrajectoryPoint] = []
            t_global = 0.0
            max_vel = 0.0
            max_acc = 0.0
            prev_yaw = 0.0
            prev_time = None
            for seg_idx, seg_time in enumerate(segment_times):
                p0 = path.waypoints[seg_idx]
                p1 = path.waypoints[seg_idx + 1]
                v0 = waypoint_vels[seg_idx]
                v1 = waypoint_vels[seg_idx + 1]
                cx = self._solve_poly_segment(p0[0], p1[0], v0[0], v1[0], seg_time)
                cy = self._solve_poly_segment(p0[1], p1[1], v0[1], v1[1], seg_time)
                cz = self._solve_poly_segment(p0[2], p1[2], v0[2], v1[2], seg_time)
                steps = max(2, int(math.ceil(seg_time / self.dt)))
                for k in range(steps):
                    tau = min(seg_time, k * self.dt)
                    px, vx, ax, _jx = self._poly_eval(cx, tau)
                    py, vy, ay, _jy = self._poly_eval(cy, tau)
                    pz, vz, az, _jz = self._poly_eval(cz, tau)
                    vel_norm = math.sqrt(vx * vx + vy * vy + vz * vz)
                    acc_norm = math.sqrt(ax * ax + ay * ay + az * az)
                    max_vel = max(max_vel, vel_norm)
                    max_acc = max(max_acc, acc_norm)
                    yaw = math.atan2(vy, vx) if abs(vx) + abs(vy) > 1e-9 else prev_yaw
                    yaw_rate = 0.0
                    if prev_time is not None:
                        dt_yaw = max(1e-6, (t_global + tau) - prev_time)
                        yaw_rate = (yaw - prev_yaw) / dt_yaw
                    all_points.append(
                        TrajectoryPoint(
                            time=t_global + tau,
                            position=(px, py, pz),
                            velocity=(vx, vy, vz),
                            acceleration=(ax, ay, az),
                            yaw=yaw,
                            yaw_rate=yaw_rate,
                        )
                    )
                    prev_yaw = yaw
                    prev_time = t_global + tau
                t_global += seg_time

            all_points.append(
                TrajectoryPoint(
                    time=t_global,
                    position=path.waypoints[-1],
                    velocity=(0.0, 0.0, 0.0),
                    acceleration=(0.0, 0.0, 0.0),
                    yaw=prev_yaw,
                    yaw_rate=0.0,
                )
            )
            last_trajectory = Trajectory(
                trajectory_id=f"traj-{uuid.uuid4().hex[:12]}",
                path_id=path.path_id,
                points=all_points,
                platform_type=constraints.platform_type,
                duration=t_global,
                max_velocity=max_vel,
                max_acceleration=max_acc,
                feasible=True,
            )
            feasibility = self.check_feasibility(last_trajectory, constraints)
            if feasibility["feasible"]:
                return last_trajectory
            time_scale *= 1.25
        if last_trajectory is None:
            raise RuntimeError("trajectory optimization failed unexpectedly")
        last_trajectory.feasible = False
        return last_trajectory

    def optimize_with_mpc(
        self,
        path: Path,
        constraints: PlatformConstraints,
        dt: float = 0.1,
        horizon: int = 20,
    ) -> Trajectory:
        try:
            import acados_template  # type: ignore  # pragma: no cover

            _ = (acados_template, dt, horizon)
            # In offline development mode we still use polynomial optimization unless
            # mission deploys acados-generated NMPC code.
            return self.optimize(path, constraints)
        except Exception:
            LOGGER.warning("acados unavailable — falling back to polynomial optimizer")
            return self.optimize(path, constraints)

    def retime(self, trajectory: Trajectory, speed_factor: float) -> Trajectory:
        if not isinstance(speed_factor, (int, float)) or float(speed_factor) <= 0:
            raise ValueError("speed_factor must be positive")
        scale = float(speed_factor)
        new_points: List[TrajectoryPoint] = []
        for p in trajectory.points:
            new_points.append(
                TrajectoryPoint(
                    time=p.time * scale,
                    position=p.position,
                    velocity=(p.velocity[0] / scale, p.velocity[1] / scale, p.velocity[2] / scale),
                    acceleration=(
                        p.acceleration[0] / (scale * scale),
                        p.acceleration[1] / (scale * scale),
                        p.acceleration[2] / (scale * scale),
                    ),
                    yaw=p.yaw,
                    yaw_rate=p.yaw_rate / scale,
                )
            )
        return Trajectory(
            trajectory_id=f"{trajectory.trajectory_id}-retimed",
            path_id=trajectory.path_id,
            points=new_points,
            platform_type=trajectory.platform_type,
            duration=trajectory.duration * scale,
            max_velocity=max(
                math.sqrt(p.velocity[0] ** 2 + p.velocity[1] ** 2 + p.velocity[2] ** 2) for p in new_points
            ),
            max_acceleration=max(
                math.sqrt(p.acceleration[0] ** 2 + p.acceleration[1] ** 2 + p.acceleration[2] ** 2) for p in new_points
            ),
            feasible=trajectory.feasible,
        )

    def check_feasibility(self, trajectory: Trajectory, constraints: PlatformConstraints) -> Dict[str, object]:
        violations: List[Dict[str, float]] = []
        for i, point in enumerate(trajectory.points):
            vel = math.sqrt(point.velocity[0] ** 2 + point.velocity[1] ** 2 + point.velocity[2] ** 2)
            acc = math.sqrt(point.acceleration[0] ** 2 + point.acceleration[1] ** 2 + point.acceleration[2] ** 2)
            if vel > constraints.max_velocity + 1e-6:
                violations.append({"time": point.time, "parameter": "velocity", "value": vel, "limit": constraints.max_velocity})
            if acc > constraints.max_acceleration + 1e-6:
                violations.append(
                    {"time": point.time, "parameter": "acceleration", "value": acc, "limit": constraints.max_acceleration}
                )
            if i > 0:
                prev = trajectory.points[i - 1]
                dt = max(1e-6, point.time - prev.time)
                jx = (point.acceleration[0] - prev.acceleration[0]) / dt
                jy = (point.acceleration[1] - prev.acceleration[1]) / dt
                jz = (point.acceleration[2] - prev.acceleration[2]) / dt
                jerk = math.sqrt(jx * jx + jy * jy + jz * jz)
                if jerk > constraints.max_jerk + 1e-6:
                    violations.append({"time": point.time, "parameter": "jerk", "value": jerk, "limit": constraints.max_jerk})
            if point.position[2] > constraints.max_altitude + 1e-6:
                violations.append(
                    {"time": point.time, "parameter": "altitude_max", "value": point.position[2], "limit": constraints.max_altitude}
                )
            if point.position[2] < constraints.min_altitude - 1e-6:
                violations.append(
                    {"time": point.time, "parameter": "altitude_min", "value": point.position[2], "limit": constraints.min_altitude}
                )
        return {"feasible": len(violations) == 0, "violations": violations}
