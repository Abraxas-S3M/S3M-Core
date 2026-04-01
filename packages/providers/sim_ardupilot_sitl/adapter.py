"""Simulation-only ArduPilot SITL adapter for autonomous flight rehearsals."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest
from packages.providers.sim_ardupilot_sitl.config import ArduPilotSITLConfig
from packages.providers.sim_ardupilot_sitl.normalizer import ArduPilotSITLNormalizer


class ArduPilotSITLAdapter(ProviderAdapter):
    provider_id = "sim-ardupilot-sitl"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = ArduPilotSITLConfig()
        self.normalizer = ArduPilotSITLNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "sim-ardupilot-sitl" / "fixtures"
        self._stub = True
        self._connected = False
        self._vehicle_type = "copter"
        self._mode = "GUIDED"
        self._armed = False
        self._mission_waypoints: list[tuple[float, float, float]] = []
        self._current_waypoint = 0
        self._gps_denied = False
        self._comms_loss = False
        self._tick = 0
        self._telemetry = {
            "lat": self.config.home_position["lat"],
            "lon": self.config.home_position["lon"],
            "alt": self.config.home_position["alt"],
            "heading": 90.0,
            "groundspeed": 0.0,
            "airspeed": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "battery_pct": 95.0,
            "battery_voltage": 15.8,
            "battery_current": 3.2,
            "gps_fix": 3,
            "satellites": 12,
            "mode": self._mode,
            "armed": self._armed,
        }

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="DRONE_UAS",
            tier="FREE",
            auth_type="none",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=[],
            description=(
                "ArduPilot Software-In-The-Loop simulator. "
                "SIMULATION ONLY - does NOT control real aircraft."
            ),
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            self._stub = True
            return True
        try:
            import pymavlink  # type: ignore  # noqa: F401

            self._stub = False
            return True
        except Exception:
            self._stub = True
            return True

    def connect(self, connection_string: str | None = None) -> dict[str, Any]:
        self.validate_credentials()
        conn = connection_string or self.config.sitl_connection
        self._connected = True
        return {
            "connected": True,
            "vehicle_type": self._vehicle_type,
            "firmware_version": "ArduPilot-SITL-Stub-4.5",
            "mode": self._mode,
            "connection": conn,
            "stub_mode": self._stub,
        }

    def _step_stub(self) -> None:
        self._tick += 1
        drift = self._tick * 0.00001
        self._telemetry["lat"] = self.config.home_position["lat"] + drift
        self._telemetry["lon"] = self.config.home_position["lon"] + drift
        if self._mode == "RTL":
            self._telemetry["alt"] = max(self.config.home_position["alt"], self._telemetry["alt"] - 0.8)
        elif self._mode == "LAND":
            self._telemetry["alt"] = max(self.config.home_position["alt"], self._telemetry["alt"] - 1.2)
        self._telemetry["battery_pct"] = max(5.0, float(self._telemetry["battery_pct"]) - 0.15)
        self._telemetry["mode"] = self._mode
        self._telemetry["armed"] = self._armed
        self._telemetry["gps_fix"] = 0 if self._gps_denied else 3
        self._telemetry["satellites"] = 0 if self._gps_denied else 12
        self._telemetry["timestamp"] = datetime.now(timezone.utc).isoformat()

    def get_telemetry(self) -> dict[str, Any]:
        self._step_stub()
        out = {k: self._telemetry.get(k) for k in self.config.telemetry_fields}
        out["timestamp"] = self._telemetry["timestamp"]
        return out

    def arm(self) -> bool:
        self._armed = True
        return True

    def disarm(self) -> bool:
        self._armed = False
        return True

    def takeoff(self, altitude_m: float = 10.0) -> dict[str, Any]:
        self._mode = "GUIDED"
        self.arm()
        self._telemetry["alt"] = float(self.config.home_position["alt"]) + float(altitude_m)
        self._telemetry["groundspeed"] = 2.0
        self._telemetry["airspeed"] = 2.0
        return {"success": True, "target_alt_m": float(altitude_m)}

    def goto(self, lat: float, lon: float, alt: float | None = None) -> dict[str, Any]:
        self._mode = "GUIDED"
        self._telemetry["lat"] = float(lat)
        self._telemetry["lon"] = float(lon)
        if alt is not None:
            self._telemetry["alt"] = float(alt)
        self._telemetry["groundspeed"] = 5.0
        return {
            "success": True,
            "target": {
                "lat": float(lat),
                "lon": float(lon),
                "alt": float(alt if alt is not None else self._telemetry["alt"]),
            },
        }

    def upload_mission(self, waypoints: list[tuple[float, float, float]]) -> dict[str, Any]:
        self._mission_waypoints = list(waypoints)
        self._current_waypoint = 0
        self._mode = "AUTO"
        return {"success": True, "waypoints": len(waypoints)}

    def set_mode(self, mode: str) -> dict[str, Any]:
        allowed = {"GUIDED", "AUTO", "RTL", "LAND", "LOITER", "ALT_HOLD", "STABILIZE", "BRAKE"}
        mode_norm = str(mode).upper()
        if mode_norm not in allowed:
            return {"success": False, "mode": mode_norm, "reason": "unsupported_mode"}
        self._mode = mode_norm
        return {"success": True, "mode": mode_norm}

    def rtl(self) -> dict[str, Any]:
        return self.set_mode("RTL")

    def land(self) -> dict[str, Any]:
        return self.set_mode("LAND")

    def get_mission_progress(self) -> dict[str, Any]:
        total = len(self._mission_waypoints)
        if total > 0 and self._current_waypoint < total:
            self._current_waypoint += 1
        remaining = max(0, total - self._current_waypoint)
        return {
            "current_waypoint": self._current_waypoint,
            "total_waypoints": total,
            "distance_to_next_m": float(remaining * 35.0),
            "eta_seconds": float(remaining * 12.0),
        }

    def get_battery(self) -> dict[str, Any]:
        return {
            "voltage": float(self._telemetry.get("battery_voltage", 0.0)),
            "current": float(self._telemetry.get("battery_current", 0.0)),
            "remaining_pct": float(self._telemetry.get("battery_pct", 0.0)),
        }

    def simulate_gps_denial(self) -> dict[str, Any]:
        self._gps_denied = True
        self._telemetry["gps_fix"] = 0
        self._telemetry["satellites"] = 0
        return {"gps_denied": True, "gps_fix_type": 0}

    def simulate_comms_loss(self) -> dict[str, Any]:
        self._comms_loss = True
        return {"comms_loss": True, "heartbeats": "stopped"}

    def feed_to_autonomy(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        return self.normalizer.telemetry_to_sensor_data(telemetry)

    def feed_to_hool(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        state = self.normalizer.telemetry_to_hool_state(telemetry)
        if self._comms_loss:
            state["comms_status"] = "lost"
            state["proposed_action"] = "rtb"
        return state

    def fetch(self, params: dict[str, Any]) -> Any:
        action = str(params.get("action", "telemetry"))
        if action == "battery":
            return self.get_battery()
        if action == "mission_progress":
            return self.get_mission_progress()
        return self.get_telemetry()

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "lat" in raw_data and "lon" in raw_data:
            return self.normalizer.normalize_telemetry(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "connected": self._connected,
            "stub_mode": self._stub,
            "mode": self._mode,
            "armed": self._armed,
        }
