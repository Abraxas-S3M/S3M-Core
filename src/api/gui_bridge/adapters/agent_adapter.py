"""Agent workspace adapter for GUI command-and-control panels.

Military context:
This adapter exposes autonomy swarm agents to operator workspaces and records
operator programming directives as training pairs for local model refinement.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from src.api.gui_bridge.models.gui_schemas import GUIAgent

try:  # Air-gap safety: swarm stack may be unavailable during partial boot.
    from src.autonomy.swarm import SwarmCoordinator as _SwarmCoordinatorType
except Exception:  # pragma: no cover - exercised in deployment failure modes
    _SwarmCoordinatorType = None

try:  # Air-gap safety: command-agent package can be disabled in austere mode.
    from services.command_agent.command_agent import CommandAgent as _CommandAgentType
except Exception:  # pragma: no cover - exercised in deployment failure modes
    _CommandAgentType = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_role(value: str) -> str:
    role = str(value or "").strip().lower()
    if role == "scout":
        return "SCOUT"
    if role in {"relay", "reserve", "follower", "ground", "maritime"}:
        return "SUPPLY"
    if role in {"cyber", "electronic_warfare"}:
        return "CYBER"
    return "SIM"


def _sanitize_status(value: str) -> str:
    state = str(value or "").strip().lower()
    if state in {"lost", "destroyed"}:
        return "error"
    if state in {"idle", "maintenance", "returning"}:
        return "idle"
    return "active"


class AgentAdapter:
    """Expose swarm agents and programming controls in GUI shape."""

    _AGENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

    def __init__(
        self,
        swarm_coordinator: Any = None,
        command_agent: Any = None,
        training_log_path: str | Path = "data/training/agent_instructions.jsonl",
    ) -> None:
        self._swarm_coordinator = (
            swarm_coordinator if swarm_coordinator is not None else self._resolve_swarm_coordinator()
        )
        self._command_agent = command_agent if command_agent is not None else self._resolve_command_agent()
        self._training_log_path = Path(training_log_path)

    def get_agents(self) -> List[GUIAgent]:
        live_agents = self._get_live_agents()
        if not live_agents:
            return self._seed_agents()
        return [self._map_agent(record) for record in live_agents]

    def get_agent_detail(self, agent_id: str) -> Dict[str, Any]:
        normalized_id = self._validate_agent_id(agent_id)
        agent = next((a for a in self.get_agents() if a.id == normalized_id), None)
        if agent is None:
            raise KeyError(f"unknown agent_id: {normalized_id}")
        logs = self._collect_agent_logs(normalized_id, limit=20)
        return {
            "agent": agent.model_dump(),
            "logs": logs,
            "updatedAt": _now_iso(),
        }

    def program_agent(self, agent_id: str, instructions: str, language: str = "EN") -> Dict[str, Any]:
        normalized_id = self._validate_agent_id(agent_id)
        normalized_instructions = self._validate_instructions(instructions)
        detail = self.get_agent_detail(normalized_id)
        route_result = self._route_to_command_agent(
            agent_id=normalized_id,
            instructions=normalized_instructions,
            language=language,
        )
        self._append_training_pair(
            agent_id=normalized_id,
            instruction=normalized_instructions,
            language=language,
            agent_state=detail["agent"],
            route_result=route_result,
        )
        return {
            "status": "accepted",
            "agentId": normalized_id,
            "route": route_result,
            "updatedAt": _now_iso(),
        }

    def _resolve_swarm_coordinator(self) -> Optional[Any]:
        if _SwarmCoordinatorType is None:
            return None
        try:
            from src.api.autonomy_routes import runtime

            coordinator = getattr(runtime, "coordinator", None)
            if coordinator is not None and hasattr(coordinator, "get_agents"):
                return coordinator
        except Exception:
            pass
        return None

    def _resolve_command_agent(self) -> Optional[Any]:
        if _CommandAgentType is None:
            return None
        try:
            return _CommandAgentType()
        except Exception:
            return None

    def _get_live_agents(self) -> List[Any]:
        if self._swarm_coordinator is None or not hasattr(self._swarm_coordinator, "get_agents"):
            return []
        try:
            rows = self._swarm_coordinator.get_agents()
            return list(rows) if isinstance(rows, list) else []
        except Exception:
            return []

    def _map_agent(self, record: Any) -> GUIAgent:
        role_value = self._extract_value(getattr(record, "role", "sim"))
        cap_value = self._extract_value(getattr(record, "capability", "air"))
        mapped_role = _sanitize_role(cap_value if cap_value == "cyber" else role_value)
        state_value = self._extract_value(getattr(record, "state", "active"))
        status = _sanitize_status(state_value)
        battery = self._to_percent(getattr(record, "battery_pct", 100.0))
        fuel = self._to_percent(getattr(record, "fuel_pct", battery))
        health = int(round((battery + fuel) / 2.0))
        mission = getattr(record, "current_mission", None)
        heartbeat = getattr(record, "last_heartbeat", None)
        return GUIAgent(
            id=str(getattr(record, "agent_id", "unknown")),
            name=str(getattr(record, "agent_id", "AGENT")).upper(),
            role=mapped_role,
            status=status,
            health=max(0, min(100, health)),
            currentTask=str(mission) if mission else None,
            function=self._role_function(mapped_role),
            uptime=self._heartbeat_to_uptime(heartbeat),
        )

    def _seed_agents(self) -> List[GUIAgent]:
        return [
            GUIAgent(
                id="scout-01",
                name="SCOUT",
                role="SCOUT",
                status="active",
                health=92,
                currentTask="Forward ISR sweep in sector ALPHA",
                function="Reconnaissance and early warning tasking",
                uptime="19h 12m",
            ),
            GUIAgent(
                id="supply-01",
                name="SUPPLY",
                role="SUPPLY",
                status="active",
                health=88,
                currentTask="Route logistics convoy through corridor DELTA",
                function="Sustainment routing and load planning",
                uptime="17h 03m",
            ),
            GUIAgent(
                id="sim-01",
                name="SIM",
                role="SIM",
                status="idle",
                health=79,
                currentTask="Standing by for COA rehearsal",
                function="Course-of-action simulation and wargaming",
                uptime="22h 41m",
            ),
            GUIAgent(
                id="cyber-01",
                name="CYBER",
                role="CYBER",
                status="active",
                health=95,
                currentTask="Monitoring contested EW/CY domain channels",
                function="Cyber defense and EW anomaly triage",
                uptime="26h 08m",
            ),
        ]

    def _collect_agent_logs(self, agent_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        logs: List[Dict[str, Any]] = []
        audit_log = getattr(self._swarm_coordinator, "audit_log", [])
        if isinstance(audit_log, list):
            for row in reversed(audit_log):
                if not isinstance(row, dict):
                    continue
                details = row.get("details", {})
                if self._log_mentions_agent(details, agent_id):
                    logs.append(
                        {
                            "timestamp": row.get("timestamp", _now_iso()),
                            "action": row.get("action", "update"),
                            "details": details if isinstance(details, dict) else {"value": str(details)},
                        }
                    )
                if len(logs) >= max(1, int(limit)):
                    break
        if not logs:
            logs = [
                {
                    "timestamp": _now_iso(),
                    "action": "status",
                    "details": {
                        "message": "No live swarm audit rows for this agent; GUI operating on local status snapshot."
                    },
                }
            ]
        return logs

    def _route_to_command_agent(self, agent_id: str, instructions: str, language: str) -> Dict[str, Any]:
        if self._command_agent is None:
            return {
                "service": "command_agent",
                "action": "program_agent",
                "result": {
                    "agent_id": agent_id,
                    "language": language,
                    "instruction": instructions,
                    "status": "queued_offline",
                },
            }

        try:
            lang_norm = "ar" if str(language).strip().lower() == "ar" else "en"
            context = self._command_agent.create_session(
                commander_id="gui-operator",
                rank="Captain",
                language=lang_norm,
                region=f"agent:{agent_id}",
            )
            payload_text = f"Program agent {agent_id}: {instructions}"
            # Tactical context: route through command-agent classifier/router for auditable C2 handling.
            intent, confidence = self._command_agent.classifier.classify(payload_text, context)
            entities = self._command_agent.classifier.extract_entities(payload_text, intent)
            route = self._command_agent.router.route(intent, entities, context, payload_text)
            route["intent"] = getattr(intent, "value", str(intent))
            route["confidence"] = float(confidence)
            route["agent_id"] = agent_id
            return route
        except Exception as exc:
            return {
                "service": "command_agent",
                "action": "program_agent",
                "result": {
                    "agent_id": agent_id,
                    "language": language,
                    "instruction": instructions,
                    "status": "router_error",
                    "error": str(exc),
                },
            }

    def _append_training_pair(
        self,
        *,
        agent_id: str,
        instruction: str,
        language: str,
        agent_state: Dict[str, Any],
        route_result: Dict[str, Any],
    ) -> None:
        row = {
            "timestamp": _now_iso(),
            "instruction": instruction,
            "input": json.dumps(
                {
                    "agentId": agent_id,
                    "language": language,
                    "agentState": agent_state,
                },
                sort_keys=True,
                default=str,
            ),
            "output": json.dumps(route_result, sort_keys=True, default=str),
            "metadata": {
                "source": "gui_bridge.agent_adapter",
                "type": "agent_programming_pair",
            },
        }
        self._training_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._training_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str))
            handle.write("\n")

    @classmethod
    def _validate_agent_id(cls, agent_id: str) -> str:
        normalized = str(agent_id or "").strip()
        if not cls._AGENT_ID_PATTERN.match(normalized):
            raise ValueError("agent_id must be 1-64 chars: [A-Za-z0-9._:-]")
        return normalized

    @staticmethod
    def _validate_instructions(instructions: str) -> str:
        text = str(instructions or "").strip()
        if not text:
            raise ValueError("instructions cannot be empty")
        if len(text) > 4000:
            raise ValueError("instructions exceed 4000 character limit")
        return text

    @staticmethod
    def _extract_value(value: Any) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _to_percent(value: Any) -> float:
        try:
            numeric = float(value)
            return max(0.0, min(100.0, numeric))
        except Exception:
            return 0.0

    @staticmethod
    def _heartbeat_to_uptime(last_heartbeat: Any) -> Optional[str]:
        if not isinstance(last_heartbeat, datetime):
            return None
        delta = datetime.now(timezone.utc) - last_heartbeat.astimezone(timezone.utc)
        total_seconds = max(0, int(delta.total_seconds()))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes:02d}m"

    @staticmethod
    def _role_function(role: str) -> str:
        mapping = {
            "SCOUT": "Reconnaissance and early warning tasking",
            "SUPPLY": "Sustainment routing and load planning",
            "SIM": "Course-of-action simulation and wargaming",
            "CYBER": "Cyber defense and EW anomaly triage",
        }
        return mapping.get(role, "General mission support")

    @staticmethod
    def _log_mentions_agent(details: Any, agent_id: str) -> bool:
        if not isinstance(details, dict):
            return False
        if details.get("agent_id") == agent_id:
            return True
        assignments = details.get("assignments")
        if isinstance(assignments, dict) and agent_id in assignments:
            return True
        assigned_agents = details.get("assigned_agents")
        if isinstance(assigned_agents, list) and agent_id in assigned_agents:
            return True
        return False
