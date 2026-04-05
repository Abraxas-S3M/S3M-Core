"""G24 USV gun-boat adapter with maritime patrol simulation."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
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
            """Advance platform simulation."""

        def get_status(self) -> dict[str, Any]:
            """Return platform status."""


@dataclass(frozen=True)
class PatrolPoint:
    """Patrol route waypoint for maritime navigation."""

    lat: float
    lon: float


def _validate_lat_lon(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("latitude must be in [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("longitude must be in [-180, 180]")


def _distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
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


class G24Adapter(PlatformAdapter):  # type: ignore[misc]
    """
    G24 USV gun boat domain adapter.

    Tactical behavior notes:
    - Simulates maritime patrol navigation with patrol routes and station-keeping.
    - Enforces 55-knot max speed.
    - Handles lost-link behavior by entering station keep near current position.
    """

    MAX_SPEED_KTS = 55.0
    CRUISE_SPEED_KTS = 32.0
    STATION_KEEP_SPEED_KTS = 6.0
    TURN_RATE_DEG_PER_SEC = 8.0
    ACCEL_KTS_PER_SEC = 2.2

    def __init__(
        self,
        platform_id: str,
        start_lat: float,
        start_lon: float,
        *,
        lost_link_timeout_s: float = 90.0,
    ) -> None:
        if not platform_id or not platform_id.strip():
            raise ValueError("platform_id must be non-empty")
        _validate_lat_lon(start_lat, start_lon)
        if lost_link_timeout_s <= 0:
            raise ValueError("lost_link_timeout_s must be positive")

        self.platform_id = platform_id.strip()
        self.lat = start_lat
        self.lon = start_lon
        self.heading_deg = 0.0
        self.speed_kts = 0.0

        self._route: list[PatrolPoint] = []
        self._route_index = 0
        self._patrol_enabled = False
        self._station_keep_center: tuple[float, float] | None = None
        self._station_keep_radius_m = 220.0
        self._station_keep_mode = False

        self.link_healthy = True
        self.lost_link_timeout_s = float(lost_link_timeout_s)
        self._link_loss_elapsed_s = 0.0
        self._last_update_monotonic = time.monotonic()

    def set_patrol_route(self, points: Iterable[tuple[float, float]]) -> None:
        route: list[PatrolPoint] = []
        for idx, point in enumerate(points):
            if len(point) != 2:
                raise ValueError(f"route point #{idx} must be (lat, lon)")
            lat = float(point[0])
            lon = float(point[1])
            _validate_lat_lon(lat, lon)
            route.append(PatrolPoint(lat=lat, lon=lon))

        if len(route) < 2:
            raise ValueError("patrol route must contain at least 2 points")

        self._route = route
        self._route_index = 0
        self._patrol_enabled = True
        self._station_keep_mode = False

    def enter_station_keep(self, *, center: tuple[float, float] | None = None, radius_m: float = 220.0) -> None:
        """Hold local area while compensating for maritime drift."""
        if center is None:
            center = (self.lat, self.lon)
        _validate_lat_lon(center[0], center[1])
        if not (50.0 <= radius_m <= 5_000.0):
            raise ValueError("radius_m must be in [50, 5000]")

        self._station_keep_center = center
        self._station_keep_radius_m = radius_m
        self._station_keep_mode = True
        self._patrol_enabled = False

    def simulate_link_loss(self, duration_s: float | None = None) -> None:
        if duration_s is not None and duration_s < 0.0:
            raise ValueError("duration_s must be >= 0")

        self.link_healthy = False
        if duration_s is None:
            self._link_loss_elapsed_s = self.lost_link_timeout_s + 1.0
        else:
            self._link_loss_elapsed_s += duration_s
        self._enforce_lost_link_behavior()

    def restore_link(self) -> None:
        self.link_healthy = True
        self._link_loss_elapsed_s = 0.0

    def _enforce_lost_link_behavior(self) -> None:
        # In denied comms conditions, station-keeping preserves maritime presence while limiting fratricide risk.
        if not self.link_healthy and self._link_loss_elapsed_s >= self.lost_link_timeout_s:
            if not self._station_keep_mode:
                self.enter_station_keep(center=(self.lat, self.lon), radius_m=300.0)

    def _steer_toward(self, target_bearing_deg: float, dt_seconds: float) -> None:
        current = self.heading_deg % 360.0
        target = target_bearing_deg % 360.0
        delta = (target - current + 540.0) % 360.0 - 180.0
        max_turn = self.TURN_RATE_DEG_PER_SEC * dt_seconds
        if abs(delta) <= max_turn:
            self.heading_deg = target
        else:
            self.heading_deg = (current + math.copysign(max_turn, delta)) % 360.0

    def _move_forward(self, dt_seconds: float) -> None:
        travel_m = self.speed_kts * KNOT_TO_MPS * dt_seconds
        self.lat, self.lon = _project_point(self.lat, self.lon, self.heading_deg, travel_m)

    def _approach_speed(self, target_speed_kts: float, dt_seconds: float) -> None:
        target_speed_kts = max(0.0, min(self.MAX_SPEED_KTS, target_speed_kts))
        max_delta = self.ACCEL_KTS_PER_SEC * dt_seconds
        delta = target_speed_kts - self.speed_kts
        if abs(delta) <= max_delta:
            self.speed_kts = target_speed_kts
        else:
            self.speed_kts += math.copysign(max_delta, delta)

    def _step_patrol(self, dt_seconds: float) -> None:
        if not self._route:
            self._approach_speed(0.0, dt_seconds)
            return

        target = self._route[self._route_index]
        distance_m = _distance_m(self.lat, self.lon, target.lat, target.lon)
        target_bearing = _bearing_deg(self.lat, self.lon, target.lat, target.lon)
        self._steer_toward(target_bearing, dt_seconds)
        self._approach_speed(self.CRUISE_SPEED_KTS, dt_seconds)
        self._move_forward(dt_seconds)

        if distance_m <= 90.0:
            self._route_index = (self._route_index + 1) % len(self._route)

    def _step_station_keep(self, dt_seconds: float) -> None:
        center = self._station_keep_center if self._station_keep_center is not None else (self.lat, self.lon)
        dist_from_center = _distance_m(self.lat, self.lon, center[0], center[1])

        if dist_from_center > self._station_keep_radius_m:
            bearing_home = _bearing_deg(self.lat, self.lon, center[0], center[1])
            self._steer_toward(bearing_home, dt_seconds)
            self._approach_speed(self.STATION_KEEP_SPEED_KTS, dt_seconds)
        else:
            drift_heading = (self.heading_deg + 25.0 * dt_seconds) % 360.0
            self._steer_toward(drift_heading, dt_seconds)
            self._approach_speed(2.0, dt_seconds)
        self._move_forward(dt_seconds)

    def tick(self, dt_seconds: float) -> None:
        if dt_seconds <= 0.0:
            raise ValueError("dt_seconds must be > 0")
        if dt_seconds > 3_600.0:
            raise ValueError("dt_seconds too large; cap is 3600 seconds")

        if not self.link_healthy:
            self._link_loss_elapsed_s += dt_seconds
            self._enforce_lost_link_behavior()

        if self._station_keep_mode:
            self._step_station_keep(dt_seconds)
        elif self._patrol_enabled:
            self._step_patrol(dt_seconds)
        else:
            self._approach_speed(0.0, dt_seconds)

        self._last_update_monotonic = time.monotonic()

    def step(self, dt_seconds: float) -> None:
        self.tick(dt_seconds)

    def get_status(self) -> dict[str, Any]:
        mode = "station_keep" if self._station_keep_mode else "patrol" if self._patrol_enabled else "idle"
        return {
            "platform_id": self.platform_id,
            "platform_type": "USV_G24",
            "mode": mode,
            "position": {"lat": self.lat, "lon": self.lon},
            "heading_deg": round(self.heading_deg, 3),
            "speed_kts": round(self.speed_kts, 3),
            "max_speed_kts": self.MAX_SPEED_KTS,
            "route_waypoints": len(self._route),
            "route_index": self._route_index,
            "station_keep_radius_m": self._station_keep_radius_m if self._station_keep_mode else None,
            "link_healthy": self.link_healthy,
            "link_loss_elapsed_s": round(self._link_loss_elapsed_s, 2),
            "lost_link_timeout_s": self.lost_link_timeout_s,
            "last_update_monotonic_s": self._last_update_monotonic,
        }

