"""Configuration for simulation-only ArduPilot SITL adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


VEHICLE_TYPES: dict[str, dict[str, object]] = {
    "copter": {
        "sim_vehicle": "ArduCopter",
        "default_frame": "quad",
        "features": ["takeoff", "land", "waypoint", "loiter", "guided", "rtl"],
    },
    "plane": {
        "sim_vehicle": "ArduPlane",
        "default_frame": "plane",
        "features": ["takeoff", "waypoint", "loiter", "rtl", "auto_land"],
    },
    "rover": {
        "sim_vehicle": "ArduRover",
        "default_frame": "rover",
        "features": ["waypoint", "guided", "rtl", "hold"],
    },
    "sub": {
        "sim_vehicle": "ArduSub",
        "default_frame": "vectored6dof",
        "features": ["depth_hold", "waypoint", "surface", "guided"],
    },
}


TELEMETRY_FIELDS = [
    "lat",
    "lon",
    "alt",
    "heading",
    "groundspeed",
    "airspeed",
    "roll",
    "pitch",
    "yaw",
    "battery_pct",
    "gps_fix",
    "satellites",
    "mode",
    "armed",
]


FLIGHT_MODES = ["STABILIZE", "ALT_HOLD", "LOITER", "RTL", "AUTO", "GUIDED", "LAND", "BRAKE"]


@dataclass(slots=True)
class ArduPilotSITLConfig:
    sitl_connection: str = field(default_factory=lambda: os.getenv("S3M_SITL_CONNECTION", "udp:127.0.0.1:14550"))
    sitl_tcp: str = "tcp:127.0.0.1:5760"
    rate_limit_rpm: int = 600
    vehicle_types: dict[str, dict[str, object]] = field(default_factory=lambda: dict(VEHICLE_TYPES))
    telemetry_fields: list[str] = field(default_factory=lambda: list(TELEMETRY_FIELDS))
    home_position: dict[str, float] = field(default_factory=lambda: {"lat": 24.71, "lon": 46.68, "alt": 612.0})
    flight_modes: list[str] = field(default_factory=lambda: list(FLIGHT_MODES))
