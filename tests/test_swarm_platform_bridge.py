#!/usr/bin/env python3
"""Tests for swarm/platform adapter bridge integration."""

from __future__ import annotations

from src.autonomy.models import AgentCapability, AgentState, CommandType, SwarmCommand
from src.autonomy.swarm.coordinator import SwarmCoordinator
from src.autonomy.swarm.platform_bridge import SwarmPlatformBridge
from src.platforms.common import HealthState, MobilityCommand, MobilityCommandType, PlatformState, PlatformType
from src.platforms.uav.warwar_adapter import WarWarAdapter
from src.platforms.ugv.hmmwv_adapter import HMMWVAdapter
from src.platforms.usv.g24_adapter import G24Adapter


def test_register_hmmwv_as_ground_agent() -> None:
    coordinator = SwarmCoordinator()
    coordinator.register_platform(HMMWVAdapter("hmmwv-1"))
    agent = coordinator.get_agent("hmmwv-1")
    assert agent is not None
    assert agent.capability == AgentCapability.GROUND


def test_register_warwar_as_air_agent() -> None:
    coordinator = SwarmCoordinator()
    coordinator.register_platform(WarWarAdapter("warwar-1"))
    agent = coordinator.get_agent("warwar-1")
    assert agent is not None
    assert agent.capability == AgentCapability.AIR


def test_register_g24_as_maritime_agent() -> None:
    coordinator = SwarmCoordinator()
    coordinator.register_platform(G24Adapter("g24-1"))
    agent = coordinator.get_agent("g24-1")
    assert agent is not None
    assert agent.capability == AgentCapability.MARITIME


def test_formation_command_translates_to_mobility_command() -> None:
    bridge = SwarmPlatformBridge(HMMWVAdapter("hmmwv-formation"))
    formation_cmd = SwarmCommand(
        command_id="cmd-form-1",
        command_type=CommandType.CHANGE_FORMATION,
        target_agents=["all"],
        parameters={
            "formation_type": "wedge",
            "spacing": 20.0,
            "target_positions": {"hmmwv-formation": (100.0, 50.0, 0.0)},
        },
        issued_by="test",
    )

    translated = bridge.translate_swarm_command(formation_cmd)

    assert len(translated) == 1
    assert isinstance(translated[0], MobilityCommand)
    assert translated[0].command_type == MobilityCommandType.MOVE_TO
    assert translated[0].target_position == (100.0, 50.0, 0.0)


def test_platform_state_updates_agent_info() -> None:
    bridge = SwarmPlatformBridge(HMMWVAdapter("hmmwv-state"))
    before = bridge.agent_info.last_heartbeat
    updated = bridge.update_from_platform_state(
        PlatformState(
            platform_id="hmmwv-state",
            platform_type=PlatformType.UGV,
            position=(25.0, 10.0, 0.0),
            health_state=HealthState.FAULT,
        )
    )

    assert updated.position == (25.0, 10.0, 0.0)
    assert updated.state == AgentState.MAINTENANCE
    assert updated.last_heartbeat >= before

