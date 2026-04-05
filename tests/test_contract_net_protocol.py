"""Tests for Contract Net mission negotiation integration."""

from __future__ import annotations

from datetime import datetime, timezone

from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    Mission,
    MissionStatus,
    MissionType,
)
from src.autonomy.swarm.contract_net import ContractNetProtocol


def _agent(agent_id: str, x: float, sensors: list[str]) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        role=AgentRole.FOLLOWER,
        state=AgentState.IDLE,
        capability=AgentCapability.AIR,
        position=(x, 0.0, 0.0),
        heading=0.0,
        speed=0.0,
        battery_pct=90.0,
        fuel_pct=80.0,
        last_heartbeat=datetime.now(timezone.utc),
        sensor_loadout=sensors,
        weapon_loadout=["basic"],
        comms_status="nominal",
    )


def _mission() -> Mission:
    return Mission(
        mission_id="mission-contract-1",
        mission_type=MissionType.PATROL,
        status=MissionStatus.PENDING,
        title="Negotiated Patrol",
        description="Contract-net assigned patrol mission",
        assigned_agents=[],
        waypoints=[(10.0, 0.0, 0.0), (20.0, 0.0, 0.0)],
        priority=2,
        rules_of_engagement="weapons_tight",
        parameters={},
    )


def test_negotiate_returns_assignments_and_bids() -> None:
    protocol = ContractNetProtocol()
    assignments = protocol.negotiate(
        mission=_mission(),
        available_agents=[
            _agent("a1", x=1.0, sensors=["eo"]),
            _agent("a2", x=2.0, sensors=["eo", "ir", "sar"]),
            _agent("a3", x=3.0, sensors=["eo"]),
        ],
    )

    assert len(assignments) == 3
    assert any(role == AgentRole.LEADER.value for role in assignments.values())
    assert any(role == AgentRole.SCOUT.value for role in assignments.values())
    assert len(protocol.last_bids) == 3
    assert protocol.negotiation_log


def test_negotiate_handles_no_available_agents() -> None:
    protocol = ContractNetProtocol()
    unavailable = _agent("a1", x=1.0, sensors=["eo"])
    unavailable.state = AgentState.MAINTENANCE
    assignments = protocol.negotiate(mission=_mission(), available_agents=[unavailable])
    assert assignments == {}
    assert protocol.last_bids == []

