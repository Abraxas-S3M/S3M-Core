"""Simulation-only DroneKit adapter for SITL mission scripting workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest
from packages.providers.sim_dronekit.config import DroneKitConfig
from packages.providers.sim_dronekit.test_scenarios import TestScenarioLibrary


class DroneKitAdapter(ProviderAdapter):
    provider_id = "sim-dronekit"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = DroneKitConfig()
        self.scenarios = TestScenarioLibrary()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "sim-dronekit" / "fixtures"
        self._stub = True
        self._connected = False
        self._mode = "GUIDED"
        self._armed = False
        self._position = {
            "lat": 24.71,
            "lon": 46.68,
            "alt": 612.0,
        }
        self._battery = {"voltage": 15.7, "current": 2.9, "remaining_pct": 90.0}

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="DRONE_UAS",
            tier="FREE",
            auth_type="none",
            rate_limit_rpm=120,
            required_env_vars=[],
            description="Python drone scripting API for SITL. SIMULATION ONLY.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            self._stub = True
            return True
        try:
            import dronekit  # type: ignore  # noqa: F401

            self._stub = False
            return True
        except Exception:
            self._stub = True
            return True

    def connect(self, connection_string: str | None = None) -> dict[str, Any]:
        self.validate_credentials()
        conn = connection_string or self.config.connection_string
        self._connected = True
        return {"connected": True, "connection_string": conn, "stub_mode": self._stub}

    def get_vehicle_state(self) -> dict[str, Any]:
        self._battery["remaining_pct"] = max(5.0, float(self._battery["remaining_pct"]) - 0.2)
        return {
            "position": dict(self._position),
            "attitude": {"roll": 0.01, "pitch": -0.02, "yaw": 1.57},
            "velocity": {"vx": 0.0, "vy": 0.0, "vz": 0.0},
            "battery": dict(self._battery),
            "gps": {"fix_type": 3, "satellites": 12},
            "mode": self._mode,
            "armed": self._armed,
            "airspeed": 0.0,
            "groundspeed": self.config.default_groundspeed_mps,
            "heading": 90.0,
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        }

    def takeoff(self, altitude_m: float = 10) -> dict[str, Any]:
        self._mode = "GUIDED"
        self._armed = True
        self._position["alt"] = 612.0 + float(altitude_m)
        return {"success": True, "altitude_m": float(altitude_m)}

    def goto(self, lat: float, lon: float, alt: float, groundspeed: float = 5) -> dict[str, Any]:
        self._mode = "GUIDED"
        self._position = {"lat": float(lat), "lon": float(lon), "alt": float(alt)}
        return {
            "success": True,
            "target": dict(self._position),
            "groundspeed": float(groundspeed),
        }

    def upload_and_execute_mission(self, waypoints: list[tuple[float, float, float]]) -> dict[str, Any]:
        self._mode = "AUTO"
        return {"mission_uploaded": True, "waypoints": len(waypoints), "mode": "AUTO"}

    def execute_test_scenario(self, scenario: str) -> dict[str, Any]:
        started = time.perf_counter()
        scenario_name = str(scenario).strip().lower()
        if scenario_name == "square_patrol":
            events = self.scenarios.square_patrol(self)
        elif scenario_name == "waypoint_mission":
            events = self.scenarios.waypoint_mission(
                self,
                [
                    (24.7105, 46.6805, 20.0),
                    (24.7110, 46.6810, 25.0),
                    (24.7115, 46.6815, 30.0),
                    (24.7120, 46.6820, 22.0),
                    (24.7125, 46.6825, 18.0),
                ],
            )
        elif scenario_name == "gps_denial_test":
            events = self.scenarios.gps_denial_test(self)
        elif scenario_name == "envelope_violation_test":
            events = self.scenarios.envelope_violation_test(
                self,
                [(24.70, 46.67), (24.72, 46.67), (24.72, 46.69), (24.70, 46.69)],
            )
        elif scenario_name == "battery_low_test":
            events = self.scenarios.battery_low_test(self)
        elif scenario_name == "comms_loss_test":
            events = self.scenarios.comms_loss_test(self)
        else:
            return {"scenario": scenario_name, "completed": False, "duration_s": 0.0, "events": []}
        duration = time.perf_counter() - started
        return {"scenario": scenario_name, "completed": True, "duration_s": round(duration, 4), "events": events}

    def rtl(self) -> dict[str, Any]:
        self._mode = "RTL"
        return {"success": True, "mode": "RTL"}

    def land(self) -> dict[str, Any]:
        self._mode = "LAND"
        self._armed = False
        self._position["alt"] = 612.0
        return {"success": True, "mode": "LAND"}

    def set_mode(self, mode: str) -> dict[str, Any]:
        self._mode = str(mode).upper()
        return {"success": True, "mode": self._mode}

    def fetch(self, params: dict[str, Any]) -> Any:
        action = str(params.get("action", "state"))
        if action == "scenario":
            return self.execute_test_scenario(str(params.get("scenario", "square_patrol")))
        return self.get_vehicle_state()

    def normalize(self, raw_data: Any) -> Any:
        return raw_data

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "connected": self._connected,
            "stub_mode": self._stub,
            "mode": self._mode,
        }
