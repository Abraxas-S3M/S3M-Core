"""Unit tests for GUI bridge agent adapter behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

import pytest

from src.api.gui_bridge.adapters.agent_adapter import AgentAdapter


class _EnumLike:
    def __init__(self, value: str) -> None:
        self.value = value


@dataclass
class _FakeAgent:
    agent_id: str
    role: _EnumLike
    state: _EnumLike
    capability: _EnumLike
    battery_pct: float
    fuel_pct: float
    current_mission: str | None
    last_heartbeat: datetime


class _FakeCoordinator:
    def __init__(self, agents: list[_FakeAgent], audit_log: list[dict]) -> None:
        self._agents = agents
        self.audit_log = audit_log

    def get_agents(self):
        return list(self._agents)


class _FakeClassifier:
    @staticmethod
    def classify(text: str, context: dict):
        class _Intent:
            value = "query_status"

        return _Intent(), 0.93

    @staticmethod
    def extract_entities(text: str, intent: object) -> dict:
        return {"units": ["SCOUT-1"], "parameters": {}}


class _FakeRouter:
    @staticmethod
    def route(intent: object, entities: dict, context: dict, raw_text: str) -> dict:
        return {
            "service": "dashboard",
            "action": "query_status",
            "result": {"status": "ok", "raw_text": raw_text},
        }


class _FakeCommandAgent:
    def __init__(self) -> None:
        self.classifier = _FakeClassifier()
        self.router = _FakeRouter()

    @staticmethod
    def create_session(commander_id: str, rank: str, language: str, region: str) -> dict:
        return {
            "commander_id": commander_id,
            "rank": rank,
            "language": language,
            "region": region,
        }


def test_get_agents_falls_back_to_seed_agents(tmp_path) -> None:
    adapter = AgentAdapter(
        swarm_coordinator=None,
        command_agent=None,
        training_log_path=tmp_path / "agent_instructions.jsonl",
    )
    agents = adapter.get_agents()
    assert len(agents) == 4
    assert [agent.role for agent in agents] == ["SCOUT", "SUPPLY", "SIM", "CYBER"]
    detail = adapter.get_agent_detail("scout-01")
    assert detail["agent"]["id"] == "scout-01"
    assert detail["logs"]


def test_get_agents_maps_live_swarm_records(tmp_path) -> None:
    agent = _FakeAgent(
        agent_id="A-101",
        role=_EnumLike("scout"),
        state=_EnumLike("active"),
        capability=_EnumLike("air"),
        battery_pct=80.0,
        fuel_pct=60.0,
        current_mission="msn-77",
        last_heartbeat=datetime.now(timezone.utc),
    )
    coordinator = _FakeCoordinator(
        agents=[agent],
        audit_log=[
            {
                "timestamp": "2026-04-08T00:00:00+00:00",
                "action": "register_agent",
                "details": {"agent_id": "A-101"},
            }
        ],
    )
    adapter = AgentAdapter(
        swarm_coordinator=coordinator,
        command_agent=None,
        training_log_path=tmp_path / "agent_instructions.jsonl",
    )

    mapped = adapter.get_agents()
    assert len(mapped) == 1
    assert mapped[0].id == "A-101"
    assert mapped[0].role == "SCOUT"
    assert mapped[0].health == 70
    assert mapped[0].currentTask == "msn-77"
    detail = adapter.get_agent_detail("A-101")
    assert detail["logs"][0]["action"] == "register_agent"


def test_program_agent_routes_and_writes_training_pair(tmp_path) -> None:
    coordinator = _FakeCoordinator(
        agents=[
            _FakeAgent(
                agent_id="A-202",
                role=_EnumLike("scout"),
                state=_EnumLike("active"),
                capability=_EnumLike("air"),
                battery_pct=90.0,
                fuel_pct=80.0,
                current_mission="msn-88",
                last_heartbeat=datetime.now(timezone.utc),
            )
        ],
        audit_log=[],
    )
    training_path = tmp_path / "agent_instructions.jsonl"
    adapter = AgentAdapter(
        swarm_coordinator=coordinator,
        command_agent=_FakeCommandAgent(),
        training_log_path=training_path,
    )

    result = adapter.program_agent(
        agent_id="A-202",
        instructions="Maintain reconnaissance orbit over sector bravo.",
    )
    assert result["status"] == "accepted"
    assert result["route"]["service"] == "dashboard"

    rows = [json.loads(line) for line in training_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["instruction"] == "Maintain reconnaissance orbit over sector bravo."
    input_payload = json.loads(row["input"])
    assert input_payload["agentId"] == "A-202"
    output_payload = json.loads(row["output"])
    assert output_payload["service"] == "dashboard"


def test_program_agent_rejects_invalid_inputs(tmp_path) -> None:
    adapter = AgentAdapter(
        swarm_coordinator=None,
        command_agent=None,
        training_log_path=tmp_path / "agent_instructions.jsonl",
    )
    with pytest.raises(ValueError):
        adapter.program_agent(agent_id="bad id", instructions="valid instruction")
    with pytest.raises(ValueError):
        adapter.program_agent(agent_id="scout-01", instructions="   ")
