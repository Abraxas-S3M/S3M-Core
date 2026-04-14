"""Core data models for interceptor drone guidance.

Military context:
These models represent the guidance-specific state that the Krechet 9C905-2
terminal maintains for each active interception: interceptor state machine,
guidance phase, computed steering commands, and intercept geometry. The existing
S3M navigation models handle general UAV flight — these handle the unique
requirements of air-to-air intercept guidance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4


class InterceptorState(str, Enum):
    """Interceptor drone lifecycle state matching Krechet operational flow."""

    PRELAUNCH = "prelaunch"
    LAUNCHED = "launched"
    RADAR_ACQUIRED = "radar_acquired"
    MIDCOURSE_GUIDED = "midcourse_guided"
    TERMINAL_APPROACH = "terminal_approach"
    AUTONOMOUS_HANDOFF = "autonomous_handoff"
    ENGAGED = "engaged"
    MISS = "miss"
    RTB = "rtb"
    LOST = "lost"


class GuidancePhase(str, Enum):
    """Active guidance computation phase."""

    BOOST = "boost"  # Post-launch climb to intercept altitude
    MIDCOURSE = "midcourse"  # C2-guided using radar updates (>300m from target)
    TERMINAL = "terminal"  # Final approach (300-200m), tightening guidance
    AUTONOMOUS = "autonomous"  # Onboard seeker lock (<200m), C2 monitors only
    POST_ENGAGE = "post_engage"


class GuidanceMode(str, Enum):
    """Guidance law selection."""

    PURE_PURSUIT = "pure_pursuit"
    LEAD_PURSUIT = "lead_pursuit"
    PROPORTIONAL_NAV = "proportional_nav"
    AUGMENTED_PN = "augmented_pn"


@dataclass
class InterceptGeometry:
    """Real-time intercept geometry between interceptor and target.

    Military context:
    The guidance computer recomputes this every update cycle. It contains
    everything needed to determine if an intercept is feasible and what
    steering corrections are required.
    """

    range_m: float = 0.0  # Slant range interceptor-to-target
    closing_velocity_mps: float = 0.0  # Rate of range decrease (positive = closing)
    time_to_intercept_s: float = 0.0  # Estimated TGO (time to go)
    line_of_sight_az_deg: float = 0.0  # LOS azimuth from interceptor to target
    line_of_sight_el_deg: float = 0.0  # LOS elevation from interceptor to target
    los_rate_az_dps: float = 0.0  # LOS azimuth rate (deg/s)
    los_rate_el_dps: float = 0.0  # LOS elevation rate (deg/s)
    lead_angle_deg: float = 0.0  # Required lead angle for collision course
    predicted_miss_distance_m: float = 0.0  # Estimated miss if no correction applied
    aspect_angle_deg: float = 0.0  # Angle off target's tail (0 = tail chase)
    crossing_angle_deg: float = 0.0  # Angle between velocity vectors

    def to_dict(self) -> Dict[str, Any]:
        return {k: round(v, 3) if isinstance(v, float) else v for k, v in self.__dict__.items()}


@dataclass
class SteeringCommand:
    """Single guidance steering command output.

    Military context:
    This is the computed maneuver command sent to the interceptor's autopilot
    every guidance update cycle. It specifies either a waypoint to fly toward
    or acceleration commands in body/inertial frame.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    commanded_heading_deg: float = 0.0
    commanded_pitch_deg: float = 0.0
    commanded_speed_mps: float = 0.0
    commanded_position: Optional[Tuple[float, float, float]] = None
    lateral_accel_mps2: float = 0.0  # Proportional nav lateral acceleration
    vertical_accel_mps2: float = 0.0  # Proportional nav vertical acceleration
    guidance_mode: GuidanceMode = GuidanceMode.PROPORTIONAL_NAV
    phase: GuidancePhase = GuidancePhase.MIDCOURSE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "heading_deg": round(self.commanded_heading_deg, 2),
            "pitch_deg": round(self.commanded_pitch_deg, 2),
            "speed_mps": round(self.commanded_speed_mps, 2),
            "position": list(self.commanded_position) if self.commanded_position else None,
            "lat_accel": round(self.lateral_accel_mps2, 3),
            "vert_accel": round(self.vertical_accel_mps2, 3),
            "mode": self.guidance_mode.value,
            "phase": self.phase.value,
        }


@dataclass
class HandoffCriteria:
    """Criteria for transitioning to autonomous terminal guidance.

    Military context:
    The Krechet hands off to the interceptor's onboard seeker at 200-300m.
    These thresholds are configurable per interceptor type.
    """

    handoff_range_m: float = 250.0  # Range at which C2 hands off to onboard
    terminal_range_m: float = 500.0  # Range at which terminal phase begins
    min_closing_velocity_mps: float = 10.0  # Abort if not closing fast enough
    max_miss_distance_m: float = 100.0  # Abort if predicted miss too large
    max_los_rate_dps: float = 30.0  # Abort if LOS rate exceeds seeker gimbal limit


@dataclass
class InterceptorConfig:
    """Interceptor drone specifications.

    Military context:
    Each interceptor type (Titan, quadrotor, fixed-wing) has different
    performance characteristics that affect guidance law parameters.
    """

    interceptor_id: str = field(default_factory=lambda: f"intc-{uuid4().hex[:8]}")
    name_en: str = "Interceptor Drone"
    name_ar: str = "طائرة اعتراض"
    platform_type: str = "fixed_wing"  # fixed_wing, quadrotor, loitering

    max_speed_mps: float = 80.0
    cruise_speed_mps: float = 55.0
    max_acceleration_mps2: float = 15.0
    max_turn_rate_dps: float = 45.0
    max_climb_rate_mps: float = 15.0
    max_altitude_m: float = 12000.0
    endurance_s: float = 600.0

    # Guidance parameters
    nav_constant: float = 4.0  # PN navigation ratio (typically 3-5)
    guidance_update_hz: float = 10.0  # Guidance loop rate
    handoff: HandoffCriteria = field(default_factory=HandoffCriteria)

    # Engagement
    kill_radius_m: float = 5.0  # Lethal radius (kinetic or proximity fuze)
    seeker_fov_deg: float = 30.0  # Onboard seeker field of view
    seeker_range_m: float = 500.0  # Onboard seeker detection range

    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interceptor_id": self.interceptor_id,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "platform_type": self.platform_type,
            "max_speed_mps": self.max_speed_mps,
            "nav_constant": self.nav_constant,
            "guidance_update_hz": self.guidance_update_hz,
            "handoff_range_m": self.handoff.handoff_range_m,
            "kill_radius_m": self.kill_radius_m,
        }


@dataclass
class GuidanceSolution:
    """Complete guidance solution for one update cycle."""

    solution_id: str = field(default_factory=lambda: f"gsol-{uuid4().hex[:8]}")
    interceptor_id: str = ""
    target_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cycle_number: int = 0
    geometry: InterceptGeometry = field(default_factory=InterceptGeometry)
    command: SteeringCommand = field(default_factory=SteeringCommand)
    phase: GuidancePhase = GuidancePhase.MIDCOURSE
    state: InterceptorState = InterceptorState.MIDCOURSE_GUIDED
    feasible: bool = True
    abort_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "solution_id": self.solution_id,
            "interceptor_id": self.interceptor_id,
            "target_id": self.target_id,
            "cycle": self.cycle_number,
            "geometry": self.geometry.to_dict(),
            "command": self.command.to_dict(),
            "phase": self.phase.value,
            "state": self.state.value,
            "feasible": self.feasible,
            "abort_reason": self.abort_reason,
        }


@dataclass
class InterceptResult:
    """Final outcome of an interception attempt."""

    result_id: str = field(default_factory=lambda: f"ires-{uuid4().hex[:8]}")
    interceptor_id: str = ""
    target_id: str = ""
    outcome: str = "pending"  # hit, miss, abort, lost_track
    miss_distance_m: float = 0.0
    engagement_time_s: float = 0.0
    guidance_cycles: int = 0
    final_phase: GuidancePhase = GuidancePhase.MIDCOURSE
    final_range_m: float = 0.0
    abort_reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
