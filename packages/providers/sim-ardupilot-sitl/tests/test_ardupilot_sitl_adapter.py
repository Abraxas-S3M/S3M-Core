from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.sim_ardupilot_sitl.adapter import ArduPilotSITLAdapter
from packages.providers.sim_ardupilot_sitl.config import FLIGHT_MODES, VEHICLE_TYPES
from packages.providers.sim_ardupilot_sitl.normalizer import ArduPilotSITLNormalizer


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_manifest_correct() -> None:
    manifest = ArduPilotSITLAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "sim-ardupilot-sitl"
    assert manifest.category == "DRONE_UAS"
    assert manifest.tier == "FREE"
    assert "simulation only" in manifest.description.lower()


def test_simulation_only_warning() -> None:
    description = ArduPilotSITLAdapter(mode="airgapped").get_manifest().description.lower()
    assert "does not control real aircraft" in description


def test_stub_mode_returns_telemetry() -> None:
    adapter = ArduPilotSITLAdapter(mode="airgapped")
    adapter.validate_credentials()
    telemetry = adapter.get_telemetry()
    assert telemetry["lat"] != 0.0
    assert telemetry["mode"] in FLIGHT_MODES


def test_vehicle_types_defined() -> None:
    assert set(VEHICLE_TYPES.keys()) == {"copter", "plane", "rover", "sub"}
    assert "takeoff" in VEHICLE_TYPES["copter"]["features"]


def test_normalize_telemetry_structure() -> None:
    telemetry = json.loads((FIXTURE_DIR / "telemetry_hovering.json").read_text(encoding="utf-8"))
    out = ArduPilotSITLNormalizer().normalize_telemetry(telemetry)
    assert {"position", "attitude", "velocity", "battery", "gps", "mode", "armed", "timestamp"}.issubset(out.keys())


def test_telemetry_to_sensor_data_bridge() -> None:
    telemetry = json.loads((FIXTURE_DIR / "telemetry_hovering.json").read_text(encoding="utf-8"))
    out = ArduPilotSITLNormalizer().telemetry_to_sensor_data(telemetry)
    assert {"position", "heading", "speed", "battery_pct", "comms_status", "mode"}.issubset(out.keys())


def test_telemetry_to_hool_state_bridge() -> None:
    telemetry = json.loads((FIXTURE_DIR / "telemetry_mission.json").read_text(encoding="utf-8"))
    out = ArduPilotSITLNormalizer().telemetry_to_hool_state(telemetry)
    assert {"current_position", "battery_pct", "fuel_pct", "comms_status", "risk_score", "proposed_action"}.issubset(out.keys())


def test_gps_denial_simulation() -> None:
    fixture = json.loads((FIXTURE_DIR / "telemetry_gps_denied.json").read_text(encoding="utf-8"))
    assert fixture["gps_fix"] == 0
    assert fixture["satellites"] == 0


def test_home_position_riyadh() -> None:
    cfg = ArduPilotSITLAdapter(mode="airgapped").config
    assert cfg.home_position["lat"] == 24.71
    assert cfg.home_position["lon"] == 46.68


def test_flight_modes_defined() -> None:
    assert set(FLIGHT_MODES) == {"STABILIZE", "ALT_HOLD", "LOITER", "RTL", "AUTO", "GUIDED", "LAND", "BRAKE"}


def test_fetch_airgapped() -> None:
    out = ArduPilotSITLAdapter(mode="airgapped").fetch({"action": "telemetry"})
    assert "lat" in out and "lon" in out and "mode" in out
