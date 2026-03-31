#!/usr/bin/env python3
"""Layer 04 full simulation demo for tactical rehearsal pipelines."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.simulation.adapters import BuiltinPhysicsEngine
from src.simulation.models import SimConfig
from src.simulation.synthetic import SyntheticDataManager
from src.simulation.wargame import OpForGenerator, ScenarioEngine, ScenarioRunner


def main() -> None:
    engine = BuiltinPhysicsEngine(SimConfig(simulator_name="builtin"))
    engine.connect()

    scenario_engine = ScenarioEngine()
    scenario = scenario_engine.load_from_yaml("configs/scenarios/urban_patrol.yaml")

    runner = ScenarioRunner(adapter=engine)
    runner.load(scenario)
    opfor = OpForGenerator(strategy="random")
    aar = runner.run(max_ticks=200, tick_dt=0.1, opfor_controller=opfor)

    print("=== Key events (first 10) ===")
    for event in aar.timeline[:10]:
        print(event)

    final_state = runner.adapter.get_state()
    print("\n=== Final entities ===")
    for entity in final_state.entities[:10]:
        print(entity.to_dict())

    print("\n=== AAR Summary ===")
    print(aar.summary())

    replay = runner.get_replay()
    print("\n=== Replay artifact ===")
    print(replay.to_dict() if replay else "No replay")

    print("\n=== Converted ThreatEvents/SensorReadings ===")
    print(f"threat_events={len(final_state.to_threat_events())}")
    print(f"sensor_readings={len(final_state.to_sensor_readings())}")

    manager = SyntheticDataManager()
    datasets = manager.generate_full_training_bundle()
    print("\n=== Synthetic training bundle ===")
    for dataset in datasets:
        print({"id": dataset.dataset_id, "name": dataset.name, "records": dataset.record_count})


if __name__ == "__main__":
    main()
