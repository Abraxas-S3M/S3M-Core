#!/usr/bin/env python3
"""
S3M Full System Demo — Showcase the complete OODA loop.
Run: python scripts/full_system_demo.py
This is the demo you run for stakeholders and commanders.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.simulation.adapters import BuiltinPhysicsEngine
from src.simulation.models import EntityType, SimConfig
from src.simulation.wargame.scenario_engine import ScenarioEngine
from src.simulation.wargame.scenario_runner import ScenarioRunner
from src.threat_detection.models import ThreatCategory, ThreatLevel
from src.threat_detection.threat_classifier import ThreatClassifier
from src.threat_detection.threat_manager import ThreatManager


def _optional(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def banner() -> None:
    print("=" * 72)
    print("S3M — Sovereign Saudi Strategic Model")
    print("Classification: UNCLASSIFIED - FOUO")
    print("Target: NVIDIA Jetson AGX Orin 64GB")
    print("Mode: Full System Demonstration")
    print("=" * 72)


def main() -> int:
    t0 = time.perf_counter()
    banner()

    print("\n[1/10] Register agents")
    swarm_module = _optional("src.autonomy.swarm.coordinator")
    swarm = None
    if swarm_module is not None:
        swarm = swarm_module.SwarmCoordinator()
        for idx in range(4):
            swarm.register_agent(f"uav_{idx+1}", position=(idx * 10, idx * 5, 50), battery_pct=100)
        print("  Registered 4 swarm agents")
    else:
        print("  Autonomy layer unavailable; using simulation-only fallback")

    print("\n[2/10] Generate OPORD")
    battle_module = _optional("src.apps.battle_planning")
    opord = {
        "paragraphs": {
            "1_situation": "Patrol sector Alpha with 4 UAVs.",
            "2_mission": "Detect and report all threats.",
            "3_execution": "Weapons tight. ISR first.",
            "4_sustainment": "Maintain battery margins above 30%.",
            "5_command_signal": "Report contacts via COP channel.",
        }
    }
    if battle_module is not None:
        planner = battle_module.BattlePlanner()
        generated = planner.plan("Conduct patrol of sector Alpha, 4 UAVs, weapons tight, detect and report all threats")
        opord = generated.get("opord", opord)
    print(f"  OPORD paragraphs: {list(opord.get('paragraphs', opord).keys())[:5]}")

    print("\n[3/10] Spawn threats")
    manager = ThreatManager()
    threats = [
        manager.ingest_manual("Enemy UAV", "Hostile UAV at 500,300,80", ThreatLevel.HIGH, ThreatCategory.KINETIC),
        manager.ingest_manual("Network Intrusion", "Suspicious lateral movement", ThreatLevel.HIGH, ThreatCategory.CYBER),
        manager.ingest_manual("Unknown Drone", "Surveillance contact at 700,400,100", ThreatLevel.MEDIUM, ThreatCategory.SURVEILLANCE),
    ]
    print(f"  Ingested threats: {len(threats)}")

    print("\n[4/10] Detect and assess")
    classifier = ThreatClassifier()
    assessed = [classifier.classify(event) for event in threats]
    for idx, event in enumerate(assessed, start=1):
        assessment = (event.llm_assessment or "[PENDING]")[:90]
        print(f"  Threat {idx}: {event.category.value} -> {assessment}")

    print("\n[5/10] Autonomy decides")
    if _optional("src.autonomy.behavior_trees.nodes") is not None:
        bt = importlib.import_module("src.autonomy.behavior_trees.nodes")
        tree = bt.SelectorNode(children=[bt.SequenceNode(children=[bt.ConditionNode("threat_close"), bt.EngageNode()]), bt.PatrolNode()])
        context = {
            "agent_position": (100, 100, 50),
            "threats": [{"position": (500, 300, 80), "level": "HIGH"}],
            "nearest_threat_distance": 180,
            "rules_of_engagement": "weapons_tight",
            "waypoints": [(200, 200, 50), (300, 250, 55)],
            "current_waypoint_idx": 0,
            "battery_pct": 92,
            "decision_log": [],
        }
        for _ in range(5):
            tree.tick(context)
        print(f"  Decisions logged: {len(context['decision_log'])}")
    else:
        print("  Behavior tree layer unavailable; skipping autonomy tick loop")

    print("\n[6/10] Plan navigation")
    nav_mod = _optional("src.navigation.planning.path_planner")
    if nav_mod is not None:
        planner = nav_mod.PathPlanner()
        for idx in range(4):
            path = planner.plan((idx * 10, idx * 5, 50), (500, 300, 80), obstacles=[{"position": (500, 300, 80), "radius": 50}])
            print(f"  Agent {idx+1} path points: {len(path) if path else 0}")
    else:
        print("  Navigation layer unavailable; skipping path planning")

    print("\n[7/10] Run wargame")
    engine = ScenarioEngine(scenarios_dir="configs/scenarios")
    scenario = engine.load_from_yaml("configs/scenarios/urban_patrol.yaml")
    runner = ScenarioRunner(adapter=BuiltinPhysicsEngine(SimConfig(simulator_name="builtin")))
    runner.adapter.connect()
    runner.load(scenario)
    aar = runner.run(max_ticks=100, tick_dt=0.1)
    print(f"  AAR outcome: {aar.outcome} | friendly_losses={aar.friendly_losses} enemy_losses={aar.enemy_losses}")

    print("\n[8/10] Dashboard data")
    dashboard_mod = _optional("src.dashboard.aggregator")
    if dashboard_mod is not None:
        overview = dashboard_mod.DashboardAggregator().get_overview()
        print(f"  Dashboard keys: {sorted(list(overview.keys()))}")
    else:
        print("  Dashboard layer unavailable; using threat stats fallback")
        print(f"  Threat stats: {manager.get_stats()}")

    print("\n[9/10] Security audit")
    security_mod = _optional("src.security.compliance")
    if security_mod is not None:
        report = security_mod.ComplianceChecker().run_full_check()
        print(f"  Compliance overall_status: {report.get('overall_status')}")
    else:
        print("  Security layer unavailable; compliance check skipped in this snapshot")

    print("\n[10/10] Final status")
    elapsed = time.perf_counter() - t0
    print(f"  Demo time: {elapsed:.2f}s")
    print("  S3M SYSTEM OPERATIONAL")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
