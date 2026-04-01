from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.sim_dronekit.adapter import DroneKitAdapter


def test_manifest_correct() -> None:
    manifest = DroneKitAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "sim-dronekit"
    assert manifest.category == "DRONE_UAS"
    assert manifest.tier == "FREE"
    assert "simulation only" in manifest.description.lower()


def test_stub_mode_without_dronekit() -> None:
    adapter = DroneKitAdapter(mode="airgapped")
    assert adapter.validate_credentials() is True
    assert adapter.connect()["stub_mode"] is True


def test_test_scenarios_defined() -> None:
    adapter = DroneKitAdapter(mode="airgapped")
    names = [
        "square_patrol",
        "waypoint_mission",
        "gps_denial_test",
        "envelope_violation_test",
        "battery_low_test",
        "comms_loss_test",
    ]
    for name in names:
        out = adapter.execute_test_scenario(name)
        assert out["scenario"] == name
        assert isinstance(out["events"], list)


def test_vehicle_state_structure() -> None:
    state = DroneKitAdapter(mode="airgapped").get_vehicle_state()
    assert {
        "position",
        "attitude",
        "velocity",
        "battery",
        "gps",
        "mode",
        "armed",
        "airspeed",
        "groundspeed",
        "heading",
        "last_heartbeat",
    }.issubset(state.keys())


def test_envelope_violation_scenario_defined() -> None:
    out = DroneKitAdapter(mode="airgapped").execute_test_scenario("envelope_violation_test")
    assert out["completed"] is True
    assert any(event["event"] == "hool_response" for event in out["events"])


def test_gps_denial_scenario_defined() -> None:
    out = DroneKitAdapter(mode="airgapped").execute_test_scenario("gps_denial_test")
    assert out["completed"] is True
    assert any(event["event"] == "gps_denied" for event in out["events"])


def test_fetch_airgapped() -> None:
    adapter = DroneKitAdapter(mode="airgapped")
    result = adapter.fetch({"action": "scenario", "scenario": "square_patrol"})
    assert result["completed"] is True
