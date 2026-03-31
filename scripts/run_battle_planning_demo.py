#!/usr/bin/env python3
"""Phase 11 battle planning demo workflow."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.apps.battle_planning import BattlePlanner


def main() -> None:
    planner = BattlePlanner()
    brief = (
        "Conduct a 4-UAV patrol of sector Alpha to detect and report enemy positions. "
        "Avoid engagement unless fired upon."
    )
    opord = planner.ops_generator.generate(brief)
    print("=== OPORD ===")
    print(json.dumps(opord, indent=2))

    scenario = planner.bridge.opord_to_scenario(opord)
    aar = planner.bridge.run_scenario(scenario)
    print("\n=== AAR SUMMARY ===")
    print(
        json.dumps(
            {
                "outcome": aar.get("outcome"),
                "friendly_losses": aar.get("friendly_losses"),
                "enemy_losses": aar.get("enemy_losses"),
                "objectives_met": aar.get("objectives_met"),
            },
            indent=2,
        )
    )

    assessment = planner.quick_assess("Enemy UAVs detected approaching our FOB from the northeast")
    print("\n=== QUICK ASSESSMENT ===")
    print(assessment)


if __name__ == "__main__":
    main()
