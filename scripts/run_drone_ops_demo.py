#!/usr/bin/env python3
"""Phase 11 drone operations demo."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.apps.drone_ops import DroneOpsModule


def main() -> None:
    module = DroneOpsModule()

    print("=== Drone Ops Demo ===")
    if module.mission_planner._swarm_coordinator is not None:
        print("SwarmCoordinator available; register agents via autonomy layer APIs.")
    else:
        print("SwarmCoordinator not available; using planner fallback agent pool.")

    request = {
        "mission_type": "PATROL",
        "waypoints": [(0, 0, 40), (300, 120, 50), (600, 250, 60), (200, 500, 45)],
        "num_agents": 2,
        "rules_of_engagement": "weapons_tight",
        "platform_type": "quadrotor",
    }
    launched = module.launch_mission(request)
    print("Mission plan:", launched["mission"])

    atr_result = module.atr.should_replan(
        [{"class": "tank", "confidence": 0.92, "threat_level": "HIGH"}]
    )
    print("Replan recommended from mock ATR:", atr_result)

    nl = module.launch_from_nl("Send two drones to recon grid 500,300 and report back")
    print("NL mission parsed:", nl["parsed_plan"])


if __name__ == "__main__":
    main()
