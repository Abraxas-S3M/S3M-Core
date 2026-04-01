from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from packages.pipelines.simulation import SimulationInteropPipeline


def test_joint_exercise_stub_mode() -> None:
    pipeline = SimulationInteropPipeline()
    out = pipeline.start_joint_exercise("GCC_Joint_Shield", vehicle_type="copter")
    assert out["federation"] == "GCC_Joint_Shield"
    assert out["sitl_connected"] is True
    assert out["dronekit_connected"] is True
    assert out["sensors_registered"] >= 1


def test_test_scenario_execution() -> None:
    pipeline = SimulationInteropPipeline()
    pipeline.start_joint_exercise("S3M_Federation")
    out = pipeline.run_test_scenario("square_patrol")
    assert out["completed"] is True
    assert out["hla_entities_published"] >= 1
    assert out["sensor_observations"] >= 1
    assert isinstance(out["events"], list)


def test_dis_hla_bridge_structure() -> None:
    pipeline = SimulationInteropPipeline()
    out = pipeline.bridge_dis_to_hla()
    assert out["hla_published"] >= 0
    assert isinstance(out["exercise_id"], int)


def test_simulation_status_all_providers() -> None:
    pipeline = SimulationInteropPipeline()
    status = pipeline.get_simulation_status()
    assert {"sim-hla", "sim-ardupilot-sitl", "sim-dronekit", "sim-sensorthings"}.issubset(status.keys())


def test_health_check() -> None:
    pipeline = SimulationInteropPipeline()
    health = pipeline.health_check()
    assert health["status"] == "ok"
    assert {"sim-hla", "sim-ardupilot-sitl", "sim-dronekit", "sim-sensorthings"}.issubset(health["providers"].keys())
