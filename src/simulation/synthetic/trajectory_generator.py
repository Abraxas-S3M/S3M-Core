"""Trajectory generation utilities for tactical movement simulation datasets."""

from __future__ import annotations

from datetime import datetime, timezone
from math import atan2, cos, sin, sqrt
from typing import Any, Dict, List, Tuple
import json
import random

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None


class TrajectoryGenerator:
    """Generate synthetic movement tracks for air and ground mission rehearsals."""

    def __init__(self, bounds: tuple = ((0, 0, 0), (1000, 1000, 200))) -> None:
        if not isinstance(bounds, tuple) or len(bounds) != 2:
            raise ValueError("bounds must be ((minx,miny,minz), (maxx,maxy,maxz))")
        self.bounds = bounds
        self._rng = random.Random(17)
        self._start_time = datetime.now(timezone.utc)

    def _clip(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        lo, hi = self.bounds
        return (
            max(float(lo[0]), min(float(hi[0]), x)),
            max(float(lo[1]), min(float(hi[1]), y)),
            max(float(lo[2]), min(float(hi[2]), z)),
        )

    def _noise(self, sigma: float) -> float:
        if np is not None:
            return float(np.random.normal(0.0, sigma))
        return self._rng.gauss(0.0, sigma)

    def generate_uav_flight(self, n_waypoints: int = 10, speed: float = 15.0, dt: float = 0.5) -> List[dict]:
        if n_waypoints <= 1:
            raise ValueError("n_waypoints must be > 1")
        if speed <= 0 or dt <= 0:
            raise ValueError("speed and dt must be positive")

        lo, hi = self.bounds
        waypoints: List[Tuple[float, float, float]] = []
        for _ in range(n_waypoints):
            waypoints.append(
                (
                    self._rng.uniform(float(lo[0]), float(hi[0])),
                    self._rng.uniform(float(lo[1]), float(hi[1])),
                    self._rng.uniform(max(20.0, float(lo[2]) + 10.0), max(25.0, float(hi[2]) - 10.0)),
                )
            )

        records: List[dict] = []
        t = 0.0
        battery = 100.0
        for idx in range(len(waypoints) - 1):
            p0 = waypoints[idx]
            p1 = waypoints[idx + 1]
            dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            distance = max(1.0, sqrt(dx * dx + dy * dy + dz * dz))
            steps = max(2, int(distance / max(1e-3, speed * dt)))
            for step in range(steps):
                alpha = step / float(steps)
                # Tactical context: smooth interpolation approximates autopilot waypoint transitions.
                x = p0[0] * (1 - alpha) + p1[0] * alpha + self._noise(1.5)
                y = p0[1] * (1 - alpha) + p1[1] * alpha + self._noise(1.5)
                z = p0[2] * (1 - alpha) + p1[2] * alpha + self._noise(0.8)
                x, y, z = self._clip(x, y, z)
                vx = dx / max(dt * steps, 1e-6)
                vy = dy / max(dt * steps, 1e-6)
                vz = dz / max(dt * steps, 1e-6)
                heading = (atan2(vy, vx) * 180.0 / 3.141592653589793 + 360.0) % 360.0
                battery = max(0.0, battery - 100.0 / max(10, n_waypoints * steps))
                records.append(
                    {
                        "timestamp": (self._start_time.timestamp() + t),
                        "x": x,
                        "y": y,
                        "z": z,
                        "vx": vx,
                        "vy": vy,
                        "vz": vz,
                        "heading": heading,
                        "speed": speed,
                        "battery_pct": battery,
                    }
                )
                t += dt
        return records

    def generate_patrol_route(self, center: tuple, radius: float, n_loops: int = 3) -> List[dict]:
        if radius <= 0 or n_loops <= 0:
            raise ValueError("radius and n_loops must be positive")
        cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
        total_points = n_loops * 120
        records: List[dict] = []
        for i in range(total_points):
            theta = 2.0 * 3.141592653589793 * (i / 120.0)
            x = cx + radius * cos(theta) + self._noise(1.0)
            y = cy + (radius * 0.7) * sin(theta) + self._noise(1.0)
            z = cz + self._noise(0.4)
            x, y, z = self._clip(x, y, z)
            records.append({"t": i * 0.5, "x": x, "y": y, "z": z})
        return records

    def generate_vehicle_route(self, start: tuple, end: tuple, speed: float = 8.0) -> List[dict]:
        if speed <= 0:
            raise ValueError("speed must be positive")
        sx, sy, _ = start
        ex, ey, _ = end
        dx, dy = ex - sx, ey - sy
        distance = max(1.0, sqrt(dx * dx + dy * dy))
        dt = 1.0
        steps = max(2, int(distance / max(1e-6, speed * dt)))
        records: List[dict] = []
        for i in range(steps + 1):
            alpha = i / steps
            x = sx * (1 - alpha) + ex * alpha + self._noise(0.7)
            y = sy * (1 - alpha) + ey * alpha + self._noise(0.7)
            if i % 25 == 0 and i > 0:
                # Convoy stop window reflects tactical checkpoint pauses.
                for _ in range(2):
                    records.append({"t": len(records), "x": x, "y": y, "z": 0.0, "speed": 0.0})
            records.append({"t": len(records), "x": x, "y": y, "z": 0.0, "speed": speed * (0.8 + 0.4 * self._rng.random())})
        return records

    def generate_evasive_maneuver(self, start: tuple, threat_position: tuple) -> List[dict]:
        sx, sy, sz = float(start[0]), float(start[1]), float(start[2])
        tx, ty, _ = float(threat_position[0]), float(threat_position[1]), float(threat_position[2])
        vx = sx - tx
        vy = sy - ty
        norm = max(1e-6, sqrt(vx * vx + vy * vy))
        ux, uy = vx / norm, vy / norm
        records: List[dict] = []
        x, y, z = sx, sy, sz
        for i in range(60):
            mag = 6.0 + (i / 10.0)
            if i > 30:
                ux, uy = -ux * 0.95, -uy * 0.95
            x += ux * mag + self._noise(0.5)
            y += uy * mag + self._noise(0.5)
            z += (1.2 if i < 30 else -0.8) + self._noise(0.2)
            x, y, z = self._clip(x, y, z)
            records.append({"t": i * 0.4, "x": x, "y": y, "z": z})
        return records

    def generate_swarm_trajectories(
        self,
        n_agents: int = 4,
        formation: str = "wedge",
        duration: float = 120.0,
    ) -> Dict[str, List[dict]]:
        if n_agents <= 0 or duration <= 0:
            raise ValueError("n_agents and duration must be positive")
        dt = 1.0
        steps = int(duration / dt)
        lo, hi = self.bounds
        cx = (float(lo[0]) + float(hi[0])) / 2.0
        cy = (float(lo[1]) + float(hi[1])) / 2.0
        cz = max(20.0, (float(lo[2]) + float(hi[2])) / 2.0)

        offsets: List[Tuple[float, float, float]] = []
        for i in range(n_agents):
            if formation == "wedge":
                offsets.append((-(i // 2) * 8.0, (1 if i % 2 else -1) * (i + 1) * 3.0, 0.0))
            else:
                offsets.append((i * 6.0, 0.0, 0.0))

        trajectories: Dict[str, List[dict]] = {f"agent_{i+1}": [] for i in range(n_agents)}
        for step in range(steps):
            phase = step / 10.0
            leader_x = cx + 180.0 * cos(phase / 2.0)
            leader_y = cy + 180.0 * sin(phase / 2.0)
            leader_z = cz + 8.0 * sin(phase / 3.0)
            for i in range(n_agents):
                ox, oy, oz = offsets[i]
                correction = 0.25 * sin(phase + i)
                x, y, z = self._clip(
                    leader_x + ox + correction + self._noise(0.4),
                    leader_y + oy + correction + self._noise(0.4),
                    leader_z + oz + self._noise(0.25),
                )
                trajectories[f"agent_{i+1}"].append({"t": step * dt, "x": x, "y": y, "z": z})
        return trajectories

    def save_trajectories(self, trajectories, filepath) -> str:
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(trajectories, handle, indent=2)
        return filepath
