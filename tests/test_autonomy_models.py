#!/usr/bin/env python3
"""Tests for Phase 6 autonomy data models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    AutonomyDecision,
    CommandType,
    DecisionType,
    Formation,
    FormationType,
    Mission,
    MissionStatus,
    MissionType,
    SwarmCommand,
)


def test_enums_expose_expected_values():
    assert AgentRole.LEADER.value == "leader"
    assert AgentState.ACTIVE.value == "active"
    assert MissionType.PATROL.value == "patrol"
    assert MissionStatus.PENDING.value == "pending"
    assert CommandType.MOVE_TO.value == "move_to"
    assert FormationType.WEDGE.value == "wedge"
    assert DecisionType.REPLAN.value == "replan"


def test_agent_info_to_dict_availability_distance():
    agent = AgentInfo(
        agent_id="a1",
        role=AgentRole.SCOUT,
        state=AgentState.IDLE,
        capability=AgentCapability.AIR,
        position=(0.0, 0.0, 0.0),
        heading=10.0,
        speed=5.0,
        battery_pct=88.0,
        fuel_pct=70.0,
        sensor_loadout=["eo"],
        weapon_loadout=["small"],
    )
    payload = agent.to_dict()
    assert payload["agent_id"] == "a1"
    assert payload["role"] == "scout"
    assert agent.is_available() is True
    assert round(agent.distance_to(3.0, 4.0, 0.0), 3) == 5.0


def test_mission_to_dict_and_duration():
    now = datetime.now(timezone.utc)
    mission = Mission(
        mission_id="m1",
        mission_type=MissionType.PATROL,
        status=MissionStatus.ACTIVE,
        title="Test",
        description="Test mission",
        assigned_agents=["a1"],
        waypoints=[(0.0, 0.0, 10.0)],
        priority=2,
        rules_of_engagement="weapons_hold",
        created_at=now,
        started_at=now - timedelta(seconds=10),
        completed_at=now,
    )
    payload = mission.to_dict()
    assert payload["mission_type"] == "patrol"
    assert mission.duration_seconds() is not None
    assert mission.duration_seconds() >= 10.0


def test_swarm_command_creation_and_expiry():
    cmd = SwarmCommand(
        command_id="cmd-1",
        command_type=CommandType.HOLD,
        target_agents=["all"],
        parameters={},
        issued_by="operator",
        ttl_seconds=0.1,
    )
    assert cmd.to_dict()["command_type"] == "hold"
    assert cmd.is_expired() is False
    time.sleep(0.12)
    assert cmd.is_expired() is True


def test_formation_compute_positions_line_and_wedge():
    line = Formation(formation_type=FormationType.LINE, spacing_meters=10.0, heading=0.0)
    out_line = line.compute_positions((0.0, 0.0, 0.0), ["a0", "a1", "a2"])
    assert out_line["a0"] == (0.0, 0.0, 0.0)
    assert out_line["a1"] != out_line["a2"]

    wedge = Formation(formation_type=FormationType.WEDGE, spacing_meters=10.0, heading=0.0)
    out_wedge = wedge.compute_positions((0.0, 0.0, 0.0), ["a0", "a1", "a2"])
    assert out_wedge["a0"] == (0.0, 0.0, 0.0)
    assert out_wedge["a1"][0] < 0.0
    assert out_wedge["a2"][0] < 0.0


def test_autonomy_decision_dict_and_audit_entry():
    decision = AutonomyDecision(
        decision_id="d1",
        timestamp=datetime.now(timezone.utc),
        decision_type=DecisionType.ENGAGE,
        agent_id="a1",
        mission_id="m1",
        context={"k": 1},
        action_taken={"action": "engage"},
        alternatives_considered=[{"option": "hold", "reason": "too risky"}],
        confidence=0.8,
        reasoning="Threat inside engagement envelope.",
        llm_consulted=False,
        requires_human_review=False,
        risk_score=0.6,
    )
    payload = decision.to_dict()
    audit = decision.to_audit_entry()
    assert payload["decision_type"] == "engage"
    assert audit["decision_id"] == "d1"
    assert "reasoning" in audit
