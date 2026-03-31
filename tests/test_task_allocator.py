"""Tests for tactical swarm task allocation logic."""

from datetime import datetime, timezone

from src.autonomy.models import AgentCapability, AgentInfo, AgentRole, AgentState, Mission, MissionStatus, MissionType
from src.autonomy.swarm.task_allocator import TaskAllocator


def _agent(agent_id: str, position=(0.0, 0.0, 0.0), capability=AgentCapability.AIR, battery=90.0) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        role=AgentRole.FOLLOWER,
        state=AgentState.IDLE,
        capability=capability,
        position=position,
        heading=0.0,
        speed=0.0,
        battery_pct=battery,
        fuel_pct=95.0,
        current_mission=None,
        last_heartbeat=datetime.now(timezone.utc),
        sensor_loadout=["eo", "ir"],
        weapon_loadout=[],
        comms_status="nominal",
    )


def _mission() -> Mission:
    return Mission(
        mission_id="m-task",
        mission_type=MissionType.PATROL,
        status=MissionStatus.PENDING,
        title="Patrol",
        description="Patrol test",
        assigned_agents=[],
        waypoints=[(100.0, 0.0, 10.0)],
        priority=2,
        rules_of_engagement="weapons_tight",
        parameters={"min_agents": 2},
    )


def test_allocate_assigns_closest_capable_leader() -> None:
    allocator = TaskAllocator()
    mission = _mission()
    agents = [
        _agent("far", position=(900.0, 0.0, 10.0)),
        _agent("near", position=(90.0, 0.0, 10.0)),
        _agent("mid", position=(300.0, 0.0, 10.0)),
    ]
    assignments = allocator.allocate(mission, agents)
    assert assignments["near"] == "leader"


def test_allocate_filters_by_capability() -> None:
    allocator = TaskAllocator()
    mission = _mission()
    agents = [
        _agent("ground-1", capability=AgentCapability.GROUND, position=(50.0, 0.0, 0.0)),
        _agent("air-1", capability=AgentCapability.AIR, position=(60.0, 0.0, 10.0)),
    ]
    assignments = allocator.allocate(mission, agents)
    assert "air-1" in assignments
    assert "ground-1" not in assignments


def test_allocate_handles_insufficient_agents() -> None:
    allocator = TaskAllocator()
    mission = _mission()
    mission.parameters["min_agents"] = 4
    assignments = allocator.allocate(mission, [_agent("only", position=(50.0, 0.0, 10.0))])
    assert assignments
    assert mission.parameters.get("understaffed") is True


def test_score_agent_range() -> None:
    allocator = TaskAllocator()
    mission = _mission()
    score = allocator.score_agent(_agent("s"), mission)
    assert 0.0 <= score <= 1.0
