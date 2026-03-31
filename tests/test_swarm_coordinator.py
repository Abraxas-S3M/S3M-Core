#!/usr/bin/env python3
"""Tests for swarm coordinator."""

from datetime import datetime, timezone

from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    CommandType,
    FormationType,
    Mission,
    MissionStatus,
    MissionType,
)
from src.autonomy.swarm.coordinator import SwarmCoordinator
from src.autonomy.swarm.swarm_protocol import SwarmProtocol


def _agent(agent_id: str, x: float = 0.0, capability: AgentCapability = AgentCapability.AIR) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        role=AgentRole.FOLLOWER,
        state=AgentState.IDLE,
        capability=capability,
        position=(x, 0.0, 0.0),
        heading=0.0,
        speed=0.0,
        battery_pct=90.0,
        fuel_pct=80.0,
        last_heartbeat=datetime.now(timezone.utc),
        sensor_loadout=["eo"],
        weapon_loadout=["basic"],
        comms_status="nominal",
    )


def _mission() -> Mission:
    return Mission(
        mission_id="m-1",
        mission_type=MissionType.PATROL,
        status=MissionStatus.PENDING,
        title="Patrol",
        description="Patrol route",
        assigned_agents=[],
        waypoints=[(10.0, 0.0, 5.0)],
        priority=2,
        rules_of_engagement="weapons_tight",
        parameters={},
    )


def test_register_remove_agents():
    coord = SwarmCoordinator(max_agents=10)
    coord.register_agent(_agent("a1"))
    assert coord.get_agent("a1") is not None
    coord.remove_agent("a1")
    assert coord.get_agent("a1") is None


def test_assign_mission_allocates_roles():
    coord = SwarmCoordinator(max_agents=10)
    coord.register_agent(_agent("a1", x=1.0))
    coord.register_agent(_agent("a2", x=2.0))
    coord.register_agent(_agent("a3", x=3.0))
    assignments = coord.assign_mission(_mission())
    assert "a1" in assignments or "a2" in assignments or "a3" in assignments
    assert any(role == "leader" for role in assignments.values())


def test_issue_command_validates_and_queues():
    coord = SwarmCoordinator(max_agents=10)
    proto = SwarmProtocol()
    cmd = proto.create_command(CommandType.HOLD, ["all"], {})
    assert coord.issue_command(cmd) is True
    assert len(coord.get_command_history()) >= 1


def test_set_formation_returns_change_command():
    coord = SwarmCoordinator(max_agents=10)
    coord.register_agent(_agent("a1"))
    coord.register_agent(_agent("a2"))
    cmd = coord.set_formation(FormationType.WEDGE, spacing=20.0)
    assert cmd.command_type == CommandType.CHANGE_FORMATION
    assert cmd.parameters["formation_type"] == FormationType.WEDGE.value


def test_emergency_stop_high_priority():
    coord = SwarmCoordinator(max_agents=10)
    cmd = coord.emergency_stop()
    assert cmd.command_type == CommandType.EMERGENCY_STOP
    assert cmd.priority == 1


def test_swarm_status_agent_counts():
    coord = SwarmCoordinator(max_agents=10)
    coord.register_agent(_agent("a1"))
    coord.register_agent(_agent("a2"))
    status = coord.get_swarm_status()
    assert status["total_agents"] == 2
