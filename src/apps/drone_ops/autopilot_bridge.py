"""Autopilot bridge for MAVLink/simulated drone control."""

from __future__ import annotations

from typing import Any
import logging
import math
import time

from src.apps._shared import clamp, normalize_coords

LOGGER = logging.getLogger(__name__)


class AutopilotBridge:
    """Bridge S3M drone commands to MAVLink or simulation backend."""

    def __init__(self, backend: str = "auto") -> None:
        self._requested_backend = backend
        self.backend = "simulated"
        self._mavutil = None
        self._conn = None
        self._connected = False
        self._last_telemetry_time = 0.0
        self._position = (0.0, 0.0, 0.0)
        self._attitude = (0.0, 0.0, 0.0)
        self._battery = 100.0
        self._last_waypoint = (0.0, 0.0, 0.0)
        self._armed = False
        self._discover_backend()

    def _discover_backend(self) -> None:
        if self._requested_backend not in {"auto", "mavlink", "simulated"}:
            raise ValueError("backend must be one of auto/mavlink/simulated")
        if self._requested_backend == "simulated":
            self.backend = "simulated"
            return
        try:
            from pymavlink import mavutil  # type: ignore

            self._mavutil = mavutil
            self.backend = "mavlink"
        except Exception:
            self.backend = "simulated"
            if self._requested_backend == "mavlink":
                LOGGER.warning("pymavlink unavailable; falling back to simulated backend")

    def connect(self, connection_string: str = "udp:127.0.0.1:14540") -> bool:
        if not isinstance(connection_string, str) or not connection_string.strip():
            raise ValueError("connection_string must be non-empty")
        if self.backend == "mavlink" and self._mavutil is not None:
            try:
                self._conn = self._mavutil.mavlink_connection(connection_string)
                self._connected = True
                return True
            except Exception:
                self._connected = False
                self.backend = "simulated"
        self._connected = True
        return True

    def _mav_command_id(self, command_name: str) -> int:
        if self._mavutil is None:
            return 0
        mapping = {
            "MOVE_TO": self._mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            "HOLD": self._mavutil.mavlink.MAV_CMD_NAV_LOITER_UNLIM,
            "RTB": self._mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
            "CHANGE_ALTITUDE": self._mavutil.mavlink.MAV_CMD_NAV_CONTINUE_AND_CHANGE_ALT,
            "EMERGENCY_STOP": self._mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        }
        return int(mapping.get(command_name, 0))

    def send_command(self, command: dict[str, Any]) -> bool:
        if not isinstance(command, dict):
            raise ValueError("command must be a dictionary")
        cmd_type = str(command.get("type", "")).upper()
        if not cmd_type:
            raise ValueError("command.type is required")
        if not self._connected:
            return False
        if self.backend == "mavlink" and self._conn is not None and self._mavutil is not None:
            try:
                command_id = self._mav_command_id(cmd_type)
                if command_id == 0:
                    return False
                self._conn.mav.command_long_send(
                    1,
                    1,
                    command_id,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                )
                return True
            except Exception:
                return False
        # Simulated mode
        if cmd_type == "MOVE_TO":
            self._last_waypoint = normalize_coords(command.get("position"), dims=3)
        elif cmd_type == "CHANGE_ALTITUDE":
            self._last_waypoint = (
                self._last_waypoint[0],
                self._last_waypoint[1],
                float(command.get("altitude", self._last_waypoint[2])),
            )
        elif cmd_type == "EMERGENCY_STOP":
            self._armed = False
        elif cmd_type == "RTB":
            self._last_waypoint = (0.0, 0.0, 0.0)
        return True

    def _advance_sim(self) -> None:
        px, py, pz = self._position
        tx, ty, tz = self._last_waypoint
        dx = tx - px
        dy = ty - py
        dz = tz - pz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist > 1e-6:
            step = min(15.0, dist)
            ratio = step / dist
            self._position = (px + dx * ratio, py + dy * ratio, pz + dz * ratio)
            self._attitude = (0.0, 0.0, math.degrees(math.atan2(dy, dx)) if abs(dx) + abs(dy) > 0 else 0.0)
            self._battery = clamp(self._battery - 0.05, 0.0, 100.0)

    def get_telemetry(self) -> dict[str, Any]:
        now = time.time()
        if self.backend == "mavlink" and self._conn is not None:
            try:
                # Non-blocking polling, tolerate missing messages.
                msg = self._conn.recv_match(blocking=False)
                if msg and msg.get_type() == "GLOBAL_POSITION_INT":
                    self._position = (
                        float(getattr(msg, "lat", 0.0)) / 1e7,
                        float(getattr(msg, "lon", 0.0)) / 1e7,
                        float(getattr(msg, "relative_alt", 0.0)) / 1000.0,
                    )
                self._last_telemetry_time = now
            except Exception:
                pass
        else:
            self._advance_sim()
            self._last_telemetry_time = now
        return {
            "position": self._position,
            "attitude": self._attitude,
            "battery_pct": self._battery,
            "airspeed": 12.0,
            "groundspeed": 10.0,
            "heading": self._attitude[2],
        }

    def arm(self) -> bool:
        self._armed = True
        return True

    def disarm(self) -> bool:
        self._armed = False
        return True

    def takeoff(self, altitude: float) -> bool:
        self._last_waypoint = (self._position[0], self._position[1], float(altitude))
        return True

    def land(self) -> bool:
        self._last_waypoint = (self._position[0], self._position[1], 0.0)
        return True

    def health_check(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "connected": self._connected,
            "armed": self._armed,
            "last_telemetry_time": self._last_telemetry_time,
        }
