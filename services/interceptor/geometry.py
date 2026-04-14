"""Intercept geometry computation for air-to-air guidance.

Military context:
The guidance computer must continuously compute the geometric relationship
between interceptor and target: range, closing velocity, line-of-sight angles
and rates, time-to-intercept, and predicted miss distance. These drive all
guidance law computations. The Krechet 9C905-2 does this at radar update rate.
"""

from __future__ import annotations

import math
from typing import Sequence

from services.interceptor.models import InterceptGeometry


def _validate_finite(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


def _validate_vec3(value: Sequence[float], *, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError(f"{field_name} must be a 3-element sequence")
    x = _validate_finite(value[0], field_name=f"{field_name}[0]")
    y = _validate_finite(value[1], field_name=f"{field_name}[1]")
    z = _validate_finite(value[2], field_name=f"{field_name}[2]")
    return (x, y, z)


class InterceptGeometryComputer:
    """Compute real-time intercept geometry from interceptor and target states."""

    def __init__(self) -> None:
        self._prev_los_az: float | None = None
        self._prev_los_el: float | None = None
        self._prev_time: float | None = None

    def reset(self) -> None:
        """Reset LOS rate history for new interception."""
        self._prev_los_az = None
        self._prev_los_el = None
        self._prev_time = None

    def compute(
        self,
        interceptor_pos: Sequence[float],
        interceptor_vel: Sequence[float],
        target_pos: Sequence[float],
        target_vel: Sequence[float],
        time_s: float = 0.0,
    ) -> InterceptGeometry:
        """Compute full intercept geometry for current state.

        Args:
            interceptor_pos: (x, y, z) in meters
            interceptor_vel: (vx, vy, vz) in m/s
            target_pos: (x, y, z) in meters
            target_vel: (vx, vy, vz) in m/s
            time_s: Current simulation/mission time in seconds
        """
        interceptor_pos_xyz = _validate_vec3(interceptor_pos, field_name="interceptor_pos")
        interceptor_vel_xyz = _validate_vec3(interceptor_vel, field_name="interceptor_vel")
        target_pos_xyz = _validate_vec3(target_pos, field_name="target_pos")
        target_vel_xyz = _validate_vec3(target_vel, field_name="target_vel")
        now_s = _validate_finite(time_s, field_name="time_s")

        # Relative position: target relative to interceptor
        rx = target_pos_xyz[0] - interceptor_pos_xyz[0]
        ry = target_pos_xyz[1] - interceptor_pos_xyz[1]
        rz = target_pos_xyz[2] - interceptor_pos_xyz[2]

        # Slant range
        range_m = math.sqrt(rx * rx + ry * ry + rz * rz)
        if range_m < 0.01:
            range_m = 0.01  # Tactical safety floor for divisions at near-fuze range.

        # Relative velocity
        dvx = target_vel_xyz[0] - interceptor_vel_xyz[0]
        dvy = target_vel_xyz[1] - interceptor_vel_xyz[1]
        dvz = target_vel_xyz[2] - interceptor_vel_xyz[2]

        # Closing velocity (negative relative range rate = closing)
        closing_velocity = -(rx * dvx + ry * dvy + rz * dvz) / range_m

        # Time to intercept
        if closing_velocity > 1.0:
            tgo = range_m / closing_velocity
        else:
            tgo = range_m / max(1.0, abs(closing_velocity))  # Fallback estimate

        # Line of sight angles
        ground_range = math.sqrt(rx * rx + ry * ry)
        los_az = math.degrees(math.atan2(rx, ry)) % 360.0  # 0=North, CW
        los_el = math.degrees(math.atan2(rz, ground_range)) if ground_range > 0.01 else (
            90.0 if rz > 0 else -90.0
        )

        # LOS rates (numerical differentiation)
        los_rate_az = 0.0
        los_rate_el = 0.0
        if self._prev_los_az is not None and self._prev_los_el is not None and self._prev_time is not None:
            dt = now_s - self._prev_time
            if dt > 0.001:
                # Tactical continuity: normalize wrap to avoid false high-rate spikes.
                daz = los_az - self._prev_los_az
                if daz > 180:
                    daz -= 360
                elif daz < -180:
                    daz += 360
                los_rate_az = daz / dt
                los_rate_el = (los_el - self._prev_los_el) / dt

        self._prev_los_az = los_az
        self._prev_los_el = los_el
        self._prev_time = now_s

        # Aspect and crossing angles
        aspect = self._aspect_angle(interceptor_pos_xyz, target_pos_xyz, target_vel_xyz)
        crossing = self._crossing_angle(interceptor_vel_xyz, target_vel_xyz)

        # Lead angle (angle between LOS and collision course)
        target_speed = math.sqrt(target_vel_xyz[0] ** 2 + target_vel_xyz[1] ** 2 + target_vel_xyz[2] ** 2)
        interceptor_speed = math.sqrt(
            interceptor_vel_xyz[0] ** 2 + interceptor_vel_xyz[1] ** 2 + interceptor_vel_xyz[2] ** 2
        )
        if interceptor_speed > 1.0 and target_speed > 1.0:
            # Lead angle from sine rule in collision triangle
            sin_lead = (target_speed / max(interceptor_speed, 1.0)) * math.sin(math.radians(crossing))
            lead_angle = math.degrees(math.asin(max(-1.0, min(1.0, sin_lead))))
        else:
            lead_angle = 0.0

        # Predicted miss distance (zero-effort miss)
        # ZEM = |R × V_rel| / |V_closing| — cross product magnitude
        cross_x = ry * dvz - rz * dvy
        cross_y = rz * dvx - rx * dvz
        cross_z = rx * dvy - ry * dvx
        cross_mag = math.sqrt(cross_x**2 + cross_y**2 + cross_z**2)
        predicted_miss = cross_mag / max(abs(closing_velocity), 1.0)

        return InterceptGeometry(
            range_m=range_m,
            closing_velocity_mps=closing_velocity,
            time_to_intercept_s=tgo,
            line_of_sight_az_deg=los_az,
            line_of_sight_el_deg=los_el,
            los_rate_az_dps=los_rate_az,
            los_rate_el_dps=los_rate_el,
            lead_angle_deg=lead_angle,
            predicted_miss_distance_m=predicted_miss,
            aspect_angle_deg=aspect,
            crossing_angle_deg=crossing,
        )

    @staticmethod
    def _aspect_angle(
        interceptor_pos: tuple[float, float, float],
        target_pos: tuple[float, float, float],
        target_vel: tuple[float, float, float],
    ) -> float:
        """Angle from target's tail to interceptor (0° = tail chase, 180° = head-on)."""
        # Vector from target to interceptor
        dx = interceptor_pos[0] - target_pos[0]
        dy = interceptor_pos[1] - target_pos[1]
        dz = interceptor_pos[2] - target_pos[2]
        ts = math.sqrt(target_vel[0] ** 2 + target_vel[1] ** 2 + target_vel[2] ** 2)
        ds = math.sqrt(dx**2 + dy**2 + dz**2)
        if ts < 0.1 or ds < 0.1:
            return 0.0
        dot = (dx * target_vel[0] + dy * target_vel[1] + dz * target_vel[2]) / (ds * ts)
        return math.degrees(math.acos(max(-1.0, min(1.0, dot))))

    @staticmethod
    def _crossing_angle(vel_a: tuple[float, float, float], vel_b: tuple[float, float, float]) -> float:
        """Angle between two velocity vectors."""
        sa = math.sqrt(vel_a[0] ** 2 + vel_a[1] ** 2 + vel_a[2] ** 2)
        sb = math.sqrt(vel_b[0] ** 2 + vel_b[1] ** 2 + vel_b[2] ** 2)
        if sa < 0.1 or sb < 0.1:
            return 0.0
        dot = (vel_a[0] * vel_b[0] + vel_a[1] * vel_b[1] + vel_a[2] * vel_b[2]) / (sa * sb)
        return math.degrees(math.acos(max(-1.0, min(1.0, dot))))
