"""Particle filtering for uncertain tactical contact kinematics.

The filter estimates contact motion and intent under noisy sensing to support
robust military decision-making in contested environments.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Dict, List, Optional, Tuple


@dataclass
class Particle:
    """Single particle state for tactical target hypothesis."""

    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    intent: float
    weight: float


class TacticalParticleFilter:
    """Bootstrap SIR particle filter with systematic resampling."""

    def __init__(self, n_particles: int = 200, dt: float = 1.0, seed: Optional[int] = None) -> None:
        if n_particles <= 0:
            raise ValueError("n_particles must be > 0")
        self.n_particles = int(n_particles)
        self.dt = float(dt)
        self._rng = random.Random(seed)
        self._particles: List[Particle] = []

    def initialize(
        self,
        position: Tuple[float, float, float],
        velocity_std: float = 2.0,
        position_std: float = 5.0,
        intent_prior: float = 0.5,
    ) -> None:
        """Initialize particle cloud around observed tactical contact."""
        px, py, pz = float(position[0]), float(position[1]), float(position[2])
        p_std = max(1e-6, float(position_std))
        v_std = max(1e-6, float(velocity_std))
        ip = max(0.0, min(1.0, float(intent_prior)))
        self._particles = []
        for _ in range(self.n_particles):
            self._particles.append(
                Particle(
                    x=px + self._rng.gauss(0.0, p_std),
                    y=py + self._rng.gauss(0.0, p_std),
                    z=pz + self._rng.gauss(0.0, p_std),
                    vx=self._rng.gauss(0.0, v_std),
                    vy=self._rng.gauss(0.0, v_std),
                    vz=self._rng.gauss(0.0, v_std * 0.5),
                    intent=max(0.0, min(1.0, ip + self._rng.gauss(0.0, 0.15))),
                    weight=1.0 / self.n_particles,
                )
            )

    def _ensure_initialized(self, observation: Dict[str, float]) -> None:
        if self._particles:
            return
        self.initialize(
            position=(
                float(observation.get("x", 0.0)),
                float(observation.get("y", 0.0)),
                float(observation.get("z", 0.0)),
            )
        )

    @staticmethod
    def _gaussian_pdf(error: float, sigma: float) -> float:
        s = max(1e-6, sigma)
        return math.exp(-(error * error) / (2.0 * s * s)) / (math.sqrt(2.0 * math.pi) * s)

    @staticmethod
    def _angle_diff(a: float, b: float) -> float:
        return ((a - b + math.pi) % (2.0 * math.pi)) - math.pi

    def predict(self, process_noise_position: float = 1.5, process_noise_velocity: float = 0.5) -> None:
        """Propagate all particles through constant-velocity dynamics."""
        if not self._particles:
            return
        pn = max(1e-6, float(process_noise_position))
        vn = max(1e-6, float(process_noise_velocity))
        for p in self._particles:
            p.vx += self._rng.gauss(0.0, vn)
            p.vy += self._rng.gauss(0.0, vn)
            p.vz += self._rng.gauss(0.0, vn * 0.5)
            p.x += p.vx * self.dt + self._rng.gauss(0.0, pn)
            p.y += p.vy * self.dt + self._rng.gauss(0.0, pn)
            p.z += p.vz * self.dt + self._rng.gauss(0.0, pn * 0.5)
            p.intent = max(0.0, min(1.0, p.intent + self._rng.gauss(0.0, 0.03)))

    def update(
        self,
        observation: Dict[str, float],
        sensor_position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        sigma_position: float = 8.0,
        sigma_bearing: float = math.radians(8.0),
        sigma_intent: float = 0.2,
    ) -> None:
        """Update particle weights with position, bearing, and intent evidence."""
        self._ensure_initialized(observation)
        if not self._particles:
            return

        sx, sy, _ = float(sensor_position[0]), float(sensor_position[1]), float(sensor_position[2])
        obs_x = float(observation.get("x", 0.0))
        obs_y = float(observation.get("y", 0.0))
        obs_z = float(observation.get("z", 0.0))
        obs_bearing = observation.get("bearing")
        obs_intent = observation.get("intent")

        total_weight = 0.0
        for p in self._particles:
            dx = p.x - obs_x
            dy = p.y - obs_y
            dz = p.z - obs_z
            dist_err = math.sqrt(dx * dx + dy * dy + dz * dz)
            w_pos = self._gaussian_pdf(dist_err, sigma_position)

            w_bearing = 1.0
            if obs_bearing is not None:
                pred_bearing = math.atan2(p.y - sy, p.x - sx)
                b_err = self._angle_diff(pred_bearing, float(obs_bearing))
                w_bearing = self._gaussian_pdf(b_err, sigma_bearing)

            w_intent = 1.0
            if obs_intent is not None:
                i_err = p.intent - max(0.0, min(1.0, float(obs_intent)))
                w_intent = self._gaussian_pdf(i_err, sigma_intent)

            p.weight = max(1e-18, w_pos * w_bearing * w_intent)
            total_weight += p.weight

        if total_weight <= 0.0:
            uniform = 1.0 / self.n_particles
            for p in self._particles:
                p.weight = uniform
        else:
            inv = 1.0 / total_weight
            for p in self._particles:
                p.weight *= inv

        self._systematic_resample_if_needed()

    def _effective_sample_size(self) -> float:
        denom = sum(p.weight * p.weight for p in self._particles)
        if denom <= 0.0:
            return 0.0
        return 1.0 / denom

    def _systematic_resample_if_needed(self) -> None:
        n_eff = self._effective_sample_size()
        if n_eff >= (0.5 * self.n_particles):
            return
        self._particles = self._systematic_resample(self._particles)

    def _systematic_resample(self, particles: List[Particle]) -> List[Particle]:
        cumulative: List[float] = []
        running = 0.0
        for p in particles:
            running += p.weight
            cumulative.append(running)
        if not cumulative:
            return []
        cumulative[-1] = 1.0

        step = 1.0 / self.n_particles
        u0 = self._rng.random() * step
        i = 0
        resampled: List[Particle] = []
        for m in range(self.n_particles):
            u = u0 + m * step
            while i < self.n_particles - 1 and cumulative[i] < u:
                i += 1
            src = particles[i]
            resampled.append(
                Particle(
                    x=src.x,
                    y=src.y,
                    z=src.z,
                    vx=src.vx,
                    vy=src.vy,
                    vz=src.vz,
                    intent=src.intent,
                    weight=1.0 / self.n_particles,
                )
            )
        return resampled

    def estimate(self) -> Dict[str, float]:
        """Return weighted mean tactical state estimate."""
        if not self._particles:
            return {"x": 0.0, "y": 0.0, "z": 0.0, "vx": 0.0, "vy": 0.0, "vz": 0.0, "intent": 0.5}
        x = sum(p.x * p.weight for p in self._particles)
        y = sum(p.y * p.weight for p in self._particles)
        z = sum(p.z * p.weight for p in self._particles)
        vx = sum(p.vx * p.weight for p in self._particles)
        vy = sum(p.vy * p.weight for p in self._particles)
        vz = sum(p.vz * p.weight for p in self._particles)
        intent = sum(p.intent * p.weight for p in self._particles)
        return {"x": x, "y": y, "z": z, "vx": vx, "vy": vy, "vz": vz, "intent": intent}

    def particles(self) -> List[Dict[str, float]]:
        """Return particle snapshot for diagnostics and XAI."""
        return [
            {
                "x": p.x,
                "y": p.y,
                "z": p.z,
                "vx": p.vx,
                "vy": p.vy,
                "vz": p.vz,
                "intent": p.intent,
                "weight": p.weight,
            }
            for p in self._particles
        ]

