#!/usr/bin/env python3
"""Wargame-focused demo for running and comparing Layer 04 scenarios."""

from __future__ import annotations

from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.simulation import (
    BuiltinPhysicsEngine,
    OpForGenerator,
    ScenarioEngine,
    ScenarioRunner,
    SimConfig,
)


def run_once(seed: int):
    random.seed(seed)
    engine = ScenarioEngine(scenarios_dir="configs/scenarios/")
    adapter = BuiltinPhysicsEngine(SimConfig(simulator_name="builtin", extra_params={"seed": seed}))
    adapter.connect()
    runner = ScenarioRunner(adapter=adapter)
    scenario = engine.load_from_yaml("configs/scenarios/swarm_vs_swarm.yaml")
    runner.load(scenario)
    opfor = OpForGenerator(strategy="scripted")
    aar = runner.run(max_ticks=300, tick_dt=0.5, opfor_controller=opfor)
    print(f"[Run seed={seed}] outcome={aar.outcome} friendly_losses={aar.friendly_losses} enemy_losses={aar.enemy_losses}")
    for event in aar.timeline[:10]:
        etype = event.get("type", event.get("event", "unknown"))
        if etype in {"entity_killed", "engagement_started"}:
            print(f"  - {etype}: {event}")
    return aar


def main() -> None:
    scenario_dir = Path("configs/scenarios")
    print("Available scenarios:")
    for yaml_file in sorted(scenario_dir.glob("*.yaml")):
        print(f" - {yaml_file.name}")

    print("\nRunning swarm_vs_swarm with scripted OPFOR...")
    aars = [run_once(seed) for seed in (1, 2, 3)]
    comparison = {
        "win_rate": sum(1 for aar in aars if aar.outcome == "victory") / len(aars),
        "avg_friendly_losses": sum(aar.friendly_losses for aar in aars) / len(aars),
        "avg_enemy_losses": sum(aar.enemy_losses for aar in aars) / len(aars),
    }
    print("\nComparison summary:", comparison)


if __name__ == "__main__":
    main()
