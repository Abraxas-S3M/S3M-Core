"""Configuration for simulation-only DroneKit mission scripting adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class DroneKitConfig:
    connection_string: str = field(default_factory=lambda: os.getenv("S3M_DRONEKIT_CONNECTION", "udp:127.0.0.1:14550"))
    default_groundspeed_mps: float = 5.0
    default_altitude_m: float = 10.0
