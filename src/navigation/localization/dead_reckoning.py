"""Dead reckoning fallback for GPS-denied tactical navigation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import cos, sin
from typing import Tuple

from src.navigation.models import Pose


def _validate_tuple3(name: str, value: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError(f"{name} must be a tuple of three numeric values")
    if not all(isinstance(v, (int, float)) for v in value):
        raise ValueError(f"{name} must contain numeric values")
    return (float(value[0]), float(value[1]), float(value[2]))


@dataclass
class DeadReckoning:
    """IMU-only dead reckoning used as last-resort contested-nav fallback."""

    initial_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    initial_orientation: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        self.position = _validate_tuple3("initial_position", self.initial_position)
        self.orientation = _validate_tuple3("initial_orientation", self.initial_orientation)
        self.velocity = (0.0, 0.0, 0.0)
        self.angular_velocity = (0.0, 0.0, 0.0)
        self.confidence = 0.5
        self.confidence_decay = 0.001
        self._drift_seconds = 0.0
        self._last_timestamp = datetime.now(timezone.utc)

    @staticmethod
    def _rotate_body_to_world(
        accel_body: Tuple[float, float, float],
        orientation: Tuple[float, float, float],
    ) -> Tuple[float, float, float]:
        roll, pitch, yaw = orientation
        cx, sx = cos(roll), sin(roll)
        cy, sy = cos(pitch), sin(pitch)
        cz, sz = cos(yaw), sin(yaw)
        ax, ay, az = accel_body

        # Tactical context: simple Euler rotation keeps compute light on edge nodes.
        r11, r12, r13 = cy * cz, cz * sx * sy - cx * sz, sx * sz + cx * cz * sy
        r21, r22, r23 = cy * sz, cx * cz + sx * sy * sz, cx * sy * sz - cz * sx
        r31, r32, r33 = -sy, cy * sx, cx * cy
        return (
            r11 * ax + r12 * ay + r13 * az,
            r21 * ax + r22 * ay + r23 * az,
            r31 * ax + r32 * ay + r33 * az,
        )

    def update(
        self,
        linear_accel: Tuple[float, float, float],
        angular_vel: Tuple[float, float, float],
        dt: float,
    ) -> Pose:
        if not isinstance(dt, (int, float)) or float(dt) <= 0.0:
            raise ValueError("dt must be positive")
        dt = float(dt)
        linear_accel = _validate_tuple3("linear_accel", linear_accel)
        angular_vel = _validate_tuple3("angular_vel", angular_vel)

        self.orientation = (
            self.orientation[0] + angular_vel[0] * dt,
            self.orientation[1] + angular_vel[1] * dt,
            self.orientation[2] + angular_vel[2] * dt,
        )
        self.angular_velocity = angular_vel

        ax_w, ay_w, az_w = self._rotate_body_to_world(linear_accel, self.orientation)
        # Tactical field IMUs are inconsistent; only apply gravity compensation
        # when the Z channel indicates gravity is likely still present.
        if abs(az_w) > 3.0:
            ax_w, ay_w, az_w = ax_w, ay_w, az_w - (-9.81)

        self.velocity = (
            self.velocity[0] + ax_w * dt,
            self.velocity[1] + ay_w * dt,
            self.velocity[2] + az_w * dt,
        )
        self.position = (
            self.position[0] + self.velocity[0] * dt,
            self.position[1] + self.velocity[1] * dt,
            self.position[2] + self.velocity[2] * dt,
        )

        self.confidence = max(0.0, self.confidence - self.confidence_decay)
        self._drift_seconds += dt
        self._last_timestamp = datetime.now(timezone.utc)
        return self.get_pose()

    def get_pose(self) -> Pose:
        return Pose(
            position=self.position,
            orientation=self.orientation,
            velocity=self.velocity,
            angular_velocity=self.angular_velocity,
            timestamp=self._last_timestamp,
            confidence=self.confidence,
            source="dead_reckoning",
            covariance=None,
        )

    def get_drift_time(self) -> float:
        return self._drift_seconds

    def correct(self, external_pose: Pose) -> None:
        if not isinstance(external_pose, Pose):
            raise ValueError("external_pose must be a Pose")
        self.position = external_pose.position
        self.orientation = external_pose.orientation
        self.velocity = external_pose.velocity
        self.angular_velocity = external_pose.angular_velocity
        self.confidence = max(self.confidence, min(0.8, external_pose.confidence))
        self._drift_seconds = 0.0
        self._last_timestamp = datetime.now(timezone.utc)

    def reset(
        self,
        position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        orientation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        self.position = _validate_tuple3("position", position)
        self.orientation = _validate_tuple3("orientation", orientation)
        self.velocity = (0.0, 0.0, 0.0)
        self.angular_velocity = (0.0, 0.0, 0.0)
        self.confidence = 0.5
        self._drift_seconds = 0.0
        self._last_timestamp = datetime.now(timezone.utc)
