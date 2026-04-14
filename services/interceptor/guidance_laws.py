"""Guidance law implementations for air-to-air intercept.

Military context:
Proportional Navigation (PN) is the standard guidance law used by virtually
all modern missile systems and the Krechet interceptor drone guidance. It
commands acceleration proportional to the line-of-sight rotation rate times
closing velocity, which drives the interceptor onto a collision course.

Three laws are provided with increasing sophistication:
1. Pure Pursuit — always fly toward current target position (simplest, worst performance)
2. Lead Pursuit — fly toward predicted future position (better for crossing targets)
3. Proportional Navigation — compute acceleration to null LOS rate (optimal for constant-speed targets)
"""

from __future__ import annotations

import math
from typing import Tuple

from services.interceptor.models import (
    GuidanceMode,
    GuidancePhase,
    InterceptGeometry,
    InterceptorConfig,
    SteeringCommand,
)


class PurePursuit:
    """Always steer toward current target position.

    Simple but inefficient — results in tail-chase curves with large
    miss distances against crossing targets. Used as fallback only.
    """

    def compute(
        self,
        geometry: InterceptGeometry,
        interceptor_pos: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        config: InterceptorConfig,
        phase: GuidancePhase = GuidancePhase.MIDCOURSE,
    ) -> SteeringCommand:
        del geometry

        dx = target_pos[0] - interceptor_pos[0]
        dy = target_pos[1] - interceptor_pos[1]
        dz = target_pos[2] - interceptor_pos[2]
        ground_range = math.sqrt(dx * dx + dy * dy)

        heading = math.degrees(math.atan2(dx, dy)) % 360.0
        pitch = math.degrees(math.atan2(dz, ground_range)) if ground_range > 0.1 else 0.0

        return SteeringCommand(
            commanded_heading_deg=heading,
            commanded_pitch_deg=pitch,
            commanded_speed_mps=config.max_speed_mps,
            commanded_position=target_pos,
            guidance_mode=GuidanceMode.PURE_PURSUIT,
            phase=phase,
        )


class LeadPursuit:
    """Steer toward predicted future target position.

    Extrapolates target position by time-to-intercept to compute a
    lead point. Better than pure pursuit for crossing targets but
    still suboptimal compared to PN.
    """

    def compute(
        self,
        geometry: InterceptGeometry,
        interceptor_pos: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
        config: InterceptorConfig,
        phase: GuidancePhase = GuidancePhase.MIDCOURSE,
    ) -> SteeringCommand:
        tgo = min(geometry.time_to_intercept_s, 60.0)  # Cap prediction horizon.
        # Predicted intercept point for current guidance update.
        px = target_pos[0] + target_vel[0] * tgo
        py = target_pos[1] + target_vel[1] * tgo
        pz = target_pos[2] + target_vel[2] * tgo

        dx = px - interceptor_pos[0]
        dy = py - interceptor_pos[1]
        dz = pz - interceptor_pos[2]
        ground_range = math.sqrt(dx * dx + dy * dy)

        heading = math.degrees(math.atan2(dx, dy)) % 360.0
        pitch = math.degrees(math.atan2(dz, ground_range)) if ground_range > 0.1 else 0.0

        return SteeringCommand(
            commanded_heading_deg=heading,
            commanded_pitch_deg=pitch,
            commanded_speed_mps=config.max_speed_mps,
            commanded_position=(px, py, pz),
            guidance_mode=GuidanceMode.LEAD_PURSUIT,
            phase=phase,
        )


class ProportionalNavigation:
    """True Proportional Navigation (TPN) guidance law.

    Military context:
    The standard guidance law for air-to-air intercept. Commands lateral
    acceleration proportional to:
        a_cmd = N × Vc × dσ/dt
    where:
        N = navigation constant (typically 3-5, higher = more aggressive)
        Vc = closing velocity
        dσ/dt = line-of-sight rotation rate

    This drives the LOS rate to zero, which geometrically means the
    interceptor is on a collision course with the target. The Krechet
    9C905-2 uses this principle for its guidance computation.
    """

    def compute(
        self,
        geometry: InterceptGeometry,
        interceptor_pos: Tuple[float, float, float],
        interceptor_vel: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
        config: InterceptorConfig,
        phase: GuidancePhase = GuidancePhase.MIDCOURSE,
    ) -> SteeringCommand:
        del target_pos, target_vel

        N = config.nav_constant
        Vc = max(geometry.closing_velocity_mps, 1.0)

        # PN acceleration commands (inertial frame)
        # Lateral (horizontal): N × Vc × LOS_rate_azimuth
        los_rate_az_rad = math.radians(geometry.los_rate_az_dps)
        # Vertical: N × Vc × LOS_rate_elevation
        los_rate_el_rad = math.radians(geometry.los_rate_el_dps)

        a_lateral = N * Vc * los_rate_az_rad
        a_vertical = N * Vc * los_rate_el_rad

        # Clamp to platform limits
        max_a = config.max_acceleration_mps2
        a_lateral = max(-max_a, min(max_a, a_lateral))
        a_vertical = max(-max_a, min(max_a, a_vertical))

        # Convert acceleration command to heading/pitch adjustments
        interceptor_speed = math.sqrt(
            interceptor_vel[0] ** 2 + interceptor_vel[1] ** 2 + interceptor_vel[2] ** 2
        )
        if interceptor_speed < 1.0:
            interceptor_speed = 1.0

        # Current heading from velocity vector
        current_heading = (
            math.degrees(math.atan2(interceptor_vel[0], interceptor_vel[1])) % 360.0
        )
        current_pitch = math.degrees(
            math.atan2(
                interceptor_vel[2],
                math.sqrt(interceptor_vel[0] ** 2 + interceptor_vel[1] ** 2),
            )
        )

        # Heading correction from lateral acceleration
        dt = 1.0 / max(config.guidance_update_hz, 1.0)
        heading_correction = math.degrees(a_lateral * dt / max(interceptor_speed, 1.0))
        pitch_correction = math.degrees(a_vertical * dt / max(interceptor_speed, 1.0))

        commanded_heading = (current_heading + heading_correction) % 360.0
        commanded_pitch = max(-60.0, min(60.0, current_pitch + pitch_correction))

        # Compute commanded position (one update step ahead)
        speed = min(
            config.max_speed_mps,
            interceptor_speed + 2.0,
        )  # Slight acceleration toward max speed.
        cmd_heading_rad = math.radians(commanded_heading)
        cmd_pitch_rad = math.radians(commanded_pitch)
        step_dist = speed * dt
        cmd_x = (
            interceptor_pos[0]
            + step_dist * math.sin(cmd_heading_rad) * math.cos(cmd_pitch_rad)
        )
        cmd_y = (
            interceptor_pos[1]
            + step_dist * math.cos(cmd_heading_rad) * math.cos(cmd_pitch_rad)
        )
        cmd_z = interceptor_pos[2] + step_dist * math.sin(cmd_pitch_rad)

        return SteeringCommand(
            commanded_heading_deg=commanded_heading,
            commanded_pitch_deg=commanded_pitch,
            commanded_speed_mps=speed,
            commanded_position=(cmd_x, cmd_y, cmd_z),
            lateral_accel_mps2=a_lateral,
            vertical_accel_mps2=a_vertical,
            guidance_mode=GuidanceMode.PROPORTIONAL_NAV,
            phase=phase,
        )
