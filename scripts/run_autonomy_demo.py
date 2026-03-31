#!/usr/bin/env python3
"""Phase 6 end-to-end autonomy demo for tactical operator validation."""

from __future__ import annotations

from datetime import datetime, timezone
import random
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.autonomy.behavior_trees import MissionExecutor, MissionTree
from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    DecisionType,
    Mission,
    MissionStatus,
    MissionType,
)
from src.autonomy.swarm import SwarmCoordinator
from src.autonomy.xai import DecisionExplainer, DecisionLog


def _seed_agents() -> list[AgentInfo]:
    return [
        AgentInfo(
            agent_id=f"drone-{idx+1}",
            role=AgentRole.FOLLOWER if idx else AgentRole.LEADER,
            state=AgentState.IDLE,
            capability=AgentCapability.AIR,
            position=(50.0 + idx * 15.0, 50.0 + idx * 5.0, 100.0),
            heading=0.0,
            speed=8.0,
            battery_pct=80.0 - idx * 5.0,
            fuel_pct=90.0 - idx * 4.0,
            sensor_loadout=["eo", "ir"] if idx % 2 == 0 else ["radar", "eo"],
            weapon_loadout=["micro_missile"],
            comms_status="nominal",
        )
        for idx in range(4)
    ]


def main() -> None:
    print("=" * 72)
    print("S3M PHASE 6 AUTONOMY DEMO")
    print("Layer 03 tactical autonomy pipeline demonstration")
    print("=" * 72)

    coordinator = SwarmCoordinator(max_agents=10)
    decision_log = DecisionLog()
    explainer = DecisionExplainer()

    agents = _seed_agents()
    for agent in agents:
        coordinator.register_agent(agent)
    print(f"Registered agents: {[agent.agent_id for agent in agents]}")

    mission = Mission(
        mission_id="demo-patrol-001",
        mission_type=MissionType.PATROL,
        status=MissionStatus.PENDING,
        title="Demo Patrol",
        description="Demonstration patrol with threat response and RTB fallback.",
        assigned_agents=[],
        waypoints=[
            (100.0, 100.0, 100.0),
            (200.0, 120.0, 100.0),
            (220.0, 220.0, 100.0),
            (120.0, 220.0, 100.0),
        ],
        priority=2,
        rules_of_engagement="weapons_tight",
        parameters={"min_agents": 3, "base_position": (50.0, 50.0, 100.0)},
    )
    assignments = coordinator.assign_mission(mission)
    coordinator.start_mission(mission.mission_id)
    print(f"Mission assignments: {assignments}")

    mission_tree = MissionTree("configs/missions/patrol.yaml")
    tree = mission_tree.build()
    executor = MissionExecutor(tree=tree, tick_rate_hz=10.0)
    context = {
        "mission_id": mission.mission_id,
        "agent_id": "drone-1",
        "battery_pct": 70.0,
        "rules_of_engagement": mission.rules_of_engagement,
        "waypoints": mission.waypoints,
        "agent_position": mission.waypoints[0],
        "base_position": mission.parameters["base_position"],
        "threats": [],
        "decision_log": [],
        "patrol_loop": True,
        "available_agents": len(assignments),
    }
    executor.start(context)

    for tick in range(50):
        if tick in {10, 25, 40}:
            context["threats"] = [
                {
                    "id": f"th-{tick}",
                    "position": (
                        context["agent_position"][0] + random.uniform(5, 25),
                        context["agent_position"][1] + random.uniform(5, 25),
                        context["agent_position"][2],
                    ),
                    "level": 0.7,
                }
            ]
            if tick == 25:
                context["rules_of_engagement"] = "weapons_free"
        status = executor.tick()
        context["battery_pct"] = max(5.0, context["battery_pct"] - 0.6)
        if status.name in {"SUCCESS", "FAILURE"}:
            break

    print("\nDecision log:")
    for decision in context["decision_log"][-12:]:
        decision_log.log(decision)
        print(
            f"- {decision.timestamp.isoformat()} "
            f"{decision.decision_type.value.upper()} "
            f"conf={decision.confidence:.2f} risk={decision.risk_score:.2f}"
        )

    engage_or_retreat = [
        d for d in context["decision_log"] if d.decision_type in {DecisionType.ENGAGE, DecisionType.RETREAT}
    ]
    if engage_or_retreat:
        selected = engage_or_retreat[-1]
        explanation = explainer.explain(selected)
        print("\nXAI explanation for latest ENGAGE/RETREAT decision:")
        print(f"Summary: {explanation['summary']}")
        print(f"Recommendation: {explanation['recommendation']}")
    else:
        print("\nNo ENGAGE/RETREAT decision generated in this run.")

    print("\nSwarm status report:")
    print(coordinator.get_swarm_status())
    print("=" * 72)


if __name__ == "__main__":
    main()
