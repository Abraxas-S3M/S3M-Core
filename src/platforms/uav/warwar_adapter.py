"""WarWar catapult-launched UAS adapter with offline flight simulation."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Protocol, runtime_checkable


EARTH_RADIUS_M = 6_371_000.0
KNOT_TO_MPS = 0.514444


try:  # Dependency from Prompt 1.
    from src.platforms.common import PlatformAdapter  # type: ignore
except Exception:  # pragma: no cover - local fallback for isolated execution.
    @runtime_checkable
    class PlatformAdapter(Protocol):
        """Fallback platform adapter protocol."""

        def step(self, dt_seconds: float) -> None:
            """Advance the platform simulation."""

        def get_status(self) -> dict[str, Any]:
            """Return platform status."""


class FlightPhase(str, Enum):
    """WarWar mission phases for tactical UAV lifecycle management."""

    GROUND = "ground"
    LAUNCH = "launch"
    AIRBORNE = "airborne"
    LOITER = "loiter"
    RTB = "rtb"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class Waypoint:
    """Simple geodetic waypoint representation."""

    lat: float
    lon: float
    alt_m: float = 800.0


def _validate_lat_lon(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("latitude must be in [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("longitude must be in [-180, 180]")


def _distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Great-circle distance using haversine."""
    a_lat_r = math.radians(a_lat)
    a_lon_r = math.radians(a_lon)
    b_lat_r = math.radians(b_lat)
    b_lon_r = math.radians(b_lon)
    d_lat = b_lat_r - a_lat_r
    d_lon = b_lon_r - a_lon_r
    h = math.sin(d_lat / 2.0) ** 2 + math.cos(a_lat_r) * math.cos(b_lat_r) * math.sin(d_lon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(max(0.0, min(1.0, h))))


def _bearing_deg(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    a_lat_r = math.radians(a_lat)
    a_lon_r = math.radians(a_lon)
    b_lat_r = math.radians(b_lat)
    b_lon_r = math.radians(b_lon)
    d_lon = b_lon_r - a_lon_r
    x = math.sin(d_lon) * math.cos(b_lat_r)
    y = math.cos(a_lat_r) * math.sin(b_lat_r) - math.sin(a_lat_r) * math.cos(b_lat_r) * math.cos(d_lon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _project_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """Project geodetic point by bearing and distance."""
    if distance_m <= 0.0:
        return lat, lon

    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    brg = math.radians(bearing_deg)
    angular = distance_m / EARTH_RADIUS_M

    lat2 = math.asin(math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    lon2_norm = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
    return math.degrees(lat2), lon2_norm


class WarWarAdapter(PlatformAdapter):  # type: ignore[misc]
    """
    WarWar catapult-launched UAS simulator.

    Tactical behavior notes:
    - Supports ISR/cueing style waypoint missions inside 60km combat radius.
    - Maintains phase transitions: ground→launch→airborne→loiter→RTB→recovered.
    - Enforces lost-link timeout with automatic RTB in contested EW conditions.
    """

    OPERATIONAL_RADIUS_KM = 60.0
    ENDURANCE_HOURS = 7.0
    MAX_SPEED_KTS = 95.0
    CRUISE_SPEED_KTS = 65.0
    LOITER_SPEED_KTS = 48.0
    CLIMB_RATE_MPS = 5.5
    DESCENT_RATE_MPS = 4.0
    RESERVE_HOURS = 0.55

    def __init__(
        self,
        platform_id: str,
        home_lat: float,
        home_lon: float,
        *,
        home_alt_m: float = 0.0,
        lost_link_timeout_s: float = 90.0,
    ) -> None:
        if not platform_id or not platform_id.strip():
            raise ValueError("platform_id must be non-empty")
        _validate_lat_lon(home_lat, home_lon)
        if home_alt_m < 0.0:
            raise ValueError("home_alt_m must be >= 0")
        if lost_link_timeout_s <= 0:
            raise ValueError("lost_link_timeout_s must be positive")

        self.platform_id = platform_id.strip()
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.home_alt_m = home_alt_m
        self.lat = home_lat
        self.lon = home_lon
        self.alt_m = home_alt_m
        self.heading_deg = 0.0
        self.speed_kts = 0.0

        self.phase = FlightPhase.GROUND
        self._phase_clock_s = 0.0
        self._mission: list[Waypoint] = []
        self._waypoint_index = 0
        self._loiter_center: tuple[float, float] | None = None
        self._loiter_radius_m = 1_200.0
        self._loiter_orbit_deg = 0.0
        self._target_alt_m = 750.0

        self.endurance_remaining_h = self.ENDURANCE_HOURS
        self.fuel_pct = 100.0

        self.lost_link_timeout_s = float(lost_link_timeout_s)
        self.link_healthy = True
        self._link_loss_elapsed_s = 0.0
        self._last_update_monotonic = time.monotonic()

    def launch(self, *, target_alt_m: float = 750.0) -> None:
        """Initiate catapult launch sequence."""
        if self.phase not in {FlightPhase.GROUND, FlightPhase.RECOVERED}:
            raise RuntimeError("launch is only valid from ground/recovered phase")
        if self.endurance_remaining_h <= 0.0:
            raise RuntimeError("insufficient fuel for launch")
        if not (100.0 <= target_alt_m <= 6_000.0):
            raise ValueError("target_alt_m must be in [100, 6000]")

        self.phase = FlightPhase.LAUNCH
        self._target_alt_m = target_alt_m
        self._phase_clock_s = 0.0
        self.speed_kts = 35.0
        self.link_healthy = True
        self._link_loss_elapsed_s = 0.0

    def set_waypoint_mission(self, waypoints: Iterable[tuple[float, float] | tuple[float, float, float]]) -> None:
        """Load waypoint mission for ISR/cueing pattern."""
        parsed: list[Waypoint] = []
        for index, raw in enumerate(waypoints):
            if len(raw) not in (2, 3):
                raise ValueError(f"waypoint #{index} must contain (lat, lon) or (lat, lon, alt_m)")
            lat = float(raw[0])
            lon = float(raw[1])
            alt_m = float(raw[2]) if len(raw) == 3 else max(400.0, self._target_alt_m)
            _validate_lat_lon(lat, lon)
            if alt_m < 50.0:
                raise ValueError(f"waypoint #{index} altitude must be >= 50m")

            range_m = _distance_m(self.home_lat, self.home_lon, lat, lon)
            if range_m > self.OPERATIONAL_RADIUS_KM * 1_000.0:
                raise ValueError(
                    f"waypoint #{index} exceeds {self.OPERATIONAL_RADIUS_KM:.0f}km operational radius"
                )
            parsed.append(Waypoint(lat=lat, lon=lon, alt_m=alt_m))

        if not parsed:
            raise ValueError("at least one waypoint is required")

        self._mission = parsed
        self._waypoint_index = 0
        if self.phase == FlightPhase.LOITER:
            self.phase = FlightPhase.AIRBORNE
            self._phase_clock_s = 0.0

    def enter_loiter(self, *, center: tuple[float, float] | None = None, radius_m: float = 1_200.0) -> None:
        """Enter circular loiter around a center point."""
        if self.phase in {FlightPhase.GROUND, FlightPhase.RECOVERED}:
            raise RuntimeError("cannot loiter while grounded")
        if not (150.0 <= radius_m <= 20_000.0):
            raise ValueError("radius_m must be in [150, 20000]")

        if center is None:
            center = (self.lat, self.lon)
        _validate_lat_lon(center[0], center[1])

        self._loiter_center = center
        self._loiter_radius_m = radius_m
        self._mission = []
        self._waypoint_index = 0
        self.phase = FlightPhase.LOITER
        self._phase_clock_s = 0.0

    def simulate_link_loss(self, duration_s: float | None = None) -> None:
        """Inject datalink denial; auto-RTB after timeout."""
        if duration_s is not None and duration_s < 0.0:
            raise ValueError("duration_s must be >= 0")

        self.link_healthy = False
        if duration_s is None:
            self._link_loss_elapsed_s = self.lost_link_timeout_s + 1.0
        else:
            self._link_loss_elapsed_s += duration_s
        self._enforce_lost_link_behavior()

    def restore_link(self) -> None:
        """Restore communications link."""
        self.link_healthy = True
        self._link_loss_elapsed_s = 0.0

    def _consume_endurance(self, dt_seconds: float) -> None:
        if self.phase in {FlightPhase.GROUND, FlightPhase.RECOVERED}:
            return

        burn_multiplier = 1.0
        if self.phase == FlightPhase.LAUNCH:
            burn_multiplier = 1.35
        elif self.phase == FlightPhase.LOITER:
            burn_multiplier = 0.85
        elif self.phase == FlightPhase.RTB:
            burn_multiplier = 0.95
        elif self.speed_kts > self.CRUISE_SPEED_KTS:
            burn_multiplier = 1.15

        burn_h = (dt_seconds / 3600.0) * burn_multiplier
        self.endurance_remaining_h = max(0.0, self.endurance_remaining_h - burn_h)
        self.fuel_pct = 100.0 * (self.endurance_remaining_h / self.ENDURANCE_HOURS)

        # Tactical reserve policy: preserve fuel for recoverable RTB under uncertain air defense/weather.
        if self.endurance_remaining_h <= self.RESERVE_HOURS and self.phase not in {FlightPhase.RTB, FlightPhase.RECOVERED}:
            self.phase = FlightPhase.RTB
            self._phase_clock_s = 0.0

    def _enforce_lost_link_behavior(self) -> None:
        if self.phase in {FlightPhase.GROUND, FlightPhase.RECOVERED}:
            return
        if not self.link_healthy and self._link_loss_elapsed_s >= self.lost_link_timeout_s:
            self.phase = FlightPhase.RTB
            self._phase_clock_s = 0.0
            self._mission = []
            self._waypoint_index = 0

    def _move_toward(self, dst_lat: float, dst_lon: float, dt_seconds: float, speed_kts: float) -> bool:
        speed_kts = max(0.0, min(self.MAX_SPEED_KTS, speed_kts))
        distance_to_target = _distance_m(self.lat, self.lon, dst_lat, dst_lon)
        if distance_to_target <= 1.0:
            self.heading_deg = _bearing_deg(self.lat, self.lon, dst_lat, dst_lon)
            self.lat = dst_lat
            self.lon = dst_lon
            self.speed_kts = speed_kts
            return True

        travel_m = speed_kts * KNOT_TO_MPS * dt_seconds
        if travel_m >= distance_to_target:
            bearing = _bearing_deg(self.lat, self.lon, dst_lat, dst_lon)
            self.lat = dst_lat
            self.lon = dst_lon
            self.speed_kts = speed_kts
            self.heading_deg = bearing
            return True

        bearing = _bearing_deg(self.lat, self.lon, dst_lat, dst_lon)
        self.lat, self.lon = _project_point(self.lat, self.lon, bearing, travel_m)
        self.heading_deg = bearing
        self.speed_kts = speed_kts
        return False

    def tick(self, dt_seconds: float) -> None:
        """Advance simulation by dt_seconds."""
        if dt_seconds <= 0.0:
            raise ValueError("dt_seconds must be > 0")
        if dt_seconds > 3_600.0:
            raise ValueError("dt_seconds too large; cap is 3600 seconds")

        self._phase_clock_s += dt_seconds
        self._last_update_monotonic = time.monotonic()

        if not self.link_healthy:
            self._link_loss_elapsed_s += dt_seconds
            self._enforce_lost_link_behavior()

        self._consume_endurance(dt_seconds)

        if self.phase == FlightPhase.GROUND:
            self.speed_kts = 0.0
            return

        if self.phase == FlightPhase.RECOVERED:
            self.speed_kts = 0.0
            self.alt_m = self.home_alt_m
            self.lat = self.home_lat
            self.lon = self.home_lon
            return

        if self.phase == FlightPhase.LAUNCH:
            self.alt_m = min(self._target_alt_m, self.alt_m + self.CLIMB_RATE_MPS * dt_seconds)
            self.speed_kts = min(self.CRUISE_SPEED_KTS, self.speed_kts + 18.0 * dt_seconds / 10.0)
            if self.alt_m >= self._target_alt_m - 1.0 or self._phase_clock_s >= 90.0:
                self.phase = FlightPhase.AIRBORNE
                self._phase_clock_s = 0.0
            return

        if self.phase == FlightPhase.AIRBORNE:
            if self._mission and self._waypoint_index < len(self._mission):
                wp = self._mission[self._waypoint_index]
                reached = self._move_toward(wp.lat, wp.lon, dt_seconds, self.CRUISE_SPEED_KTS)
                if self.alt_m < wp.alt_m:
                    self.alt_m = min(wp.alt_m, self.alt_m + self.CLIMB_RATE_MPS * dt_seconds)
                else:
                    self.alt_m = max(wp.alt_m, self.alt_m - self.DESCENT_RATE_MPS * dt_seconds)
                if reached:
                    self._waypoint_index += 1
                    if self._waypoint_index >= len(self._mission):
                        self.enter_loiter(center=(self.lat, self.lon))
                return
            self.enter_loiter(center=(self.lat, self.lon))
            return

        if self.phase == FlightPhase.LOITER:
            center = self._loiter_center if self._loiter_center is not None else (self.lat, self.lon)
            tangential_mps = self.LOITER_SPEED_KTS * KNOT_TO_MPS
            angular_step = tangential_mps * dt_seconds / max(50.0, self._loiter_radius_m)
            self._loiter_orbit_deg = (self._loiter_orbit_deg + math.degrees(angular_step)) % 360.0
            target_lat, target_lon = _project_point(center[0], center[1], self._loiter_orbit_deg, self._loiter_radius_m)
            self._move_toward(target_lat, target_lon, dt_seconds, self.LOITER_SPEED_KTS)
            self.alt_m = max(300.0, self.alt_m)
            return

        if self.phase == FlightPhase.RTB:
            remaining_home_m = _distance_m(self.lat, self.lon, self.home_lat, self.home_lon)
            target_speed = self.CRUISE_SPEED_KTS if remaining_home_m > 1_500.0 else 30.0
            reached = self._move_toward(self.home_lat, self.home_lon, dt_seconds, target_speed)
            if remaining_home_m <= 2_000.0:
                self.alt_m = max(self.home_alt_m, self.alt_m - self.DESCENT_RATE_MPS * dt_seconds)
            if reached and self.alt_m <= self.home_alt_m + 1.0:
                self.phase = FlightPhase.RECOVERED
                self._phase_clock_s = 0.0
                self.speed_kts = 0.0
            return

    def step(self, dt_seconds: float) -> None:
        """Protocol-compatible simulation step."""
        self.tick(dt_seconds)

    def get_status(self) -> dict[str, Any]:
        """Protocol-compatible status snapshot."""
        return {
            "platform_id": self.platform_id,
            "platform_type": "UAV_WARWAR",
            "phase": self.phase.value,
            "position": {"lat": self.lat, "lon": self.lon, "alt_m": self.alt_m},
            "heading_deg": self.heading_deg,
            "speed_kts": self.speed_kts,
            "fuel_pct": round(self.fuel_pct, 2),
            "endurance_remaining_h": round(self.endurance_remaining_h, 3),
            "link_healthy": self.link_healthy,
            "link_loss_elapsed_s": round(self._link_loss_elapsed_s, 1),
            "lost_link_timeout_s": self.lost_link_timeout_s,
            "mission_waypoints": len(self._mission),
            "mission_index": self._waypoint_index,
            "range_from_home_km": round(_distance_m(self.lat, self.lon, self.home_lat, self.home_lon) / 1000.0, 3),
            "last_update_monotonic_s": self._last_update_monotonic,
        }

