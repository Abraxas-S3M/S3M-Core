#!/usr/bin/env python3
"""Demonstrate swarm coordination and natural-language command control."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    FormationType,
)
from src.autonomy.swarm import NLCommander, SwarmCoordinator


def build_agent(idx: int) -> AgentInfo:
    """Create sample drone state for tactical swarm demonstration."""
    return AgentInfo(
        agent_id=f"s{idx}",
        role=AgentRole.FOLLOWER if idx else AgentRole.LEADER,
        state=AgentState.IDLE,
        capability=AgentCapability.AIR,
        position=(100.0 + idx * 20.0, 200.0 + idx * 5.0, 40.0),
        heading=45.0,
        speed=8.0,
        battery_pct=95.0 - idx * 4.0,
        fuel_pct=90.0 - idx * 3.0,
        current_mission=None,
        last_heartbeat=datetime.now(timezone.utc),
        sensor_loadout=["eo", "ir"],
        weapon_loadout=["jammer"],
        comms_status="nominal",
    )


def main() -> None:
    coordinator = SwarmCoordinator(max_agents=10)
    nl = NLCommander()

    for idx in range(6):
        coordinator.register_agent(build_agent(idx))

    wedge_cmd = coordinator.set_formation(FormationType.WEDGE, spacing=20.0)
    print("WEDGE command:", wedge_cmd.to_dict())
    print("WEDGE target positions:", coordinator.current_formation["target_positions"])

    old_positions = {
        aid: agent.position for aid, agent in coordinator.agents.items()
    }
    diamond_cmd = coordinator.set_formation(FormationType.DIAMOND, spacing=18.0)
    target_positions = coordinator.current_formation["target_positions"]
    transitioned = coordinator.formation_controller.transition(old_positions, target_positions, step_fraction=0.4)
    print("\nDIAMOND command:", diamond_cmd.to_dict())
    print("Transitioned positions (40%):", transitioned)

    english = nl.parse_command("move all agents to grid 500 300 100")
    coordinator.issue_command(english)
    print("\nNL English command:", english.to_dict())

    arabic = nl.parse_arabic_command("عودة للقاعدة")
    coordinator.issue_command(arabic)
    print("NL Arabic command:", arabic.to_dict())

    print("\nCommand history:")
    for command in coordinator.get_command_history(limit=6):
        print("-", command.command_type.value, command.parameters)

    print("\nSwarm status:")
    print(coordinator.get_swarm_status())


if __name__ == "__main__":
    main()
