"""Swarm command protocol utilities for tactical C2 messaging.

Provides secure command creation, validation, and serialization for reliable
agent control in air-gapped operational environments.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Dict, List, Tuple
import uuid

from src.autonomy.models import CommandType, SwarmCommand


class SwarmProtocol:
    """Protocol helper for swarm command lifecycle management."""

    def create_command(
        self,
        command_type: CommandType,
        target_agents: List[str],
        parameters: dict,
        issued_by: str = "autonomy",
        priority: int = 3,
        ttl: float = 60.0,
    ) -> SwarmCommand:
        """Create validated command with tactical metadata."""
        return SwarmCommand(
            command_id=f"cmd-{uuid.uuid4().hex[:12]}",
            command_type=command_type,
            target_agents=list(target_agents),
            parameters=dict(parameters or {}),
            issued_by=issued_by,
            issued_at=datetime.now(timezone.utc),
            priority=int(priority),
            ttl_seconds=float(ttl),
        )

    def validate_command(self, command: SwarmCommand) -> Tuple[bool, str]:
        """Validate command fields, targets, and expiration semantics."""
        if not isinstance(command, SwarmCommand):
            return False, "invalid command object"
        if not command.target_agents:
            return False, "target_agents cannot be empty"
        if command.priority < 1 or command.priority > 5:
            return False, "priority must be between 1 and 5"
        if command.ttl_seconds <= 0:
            return False, "ttl_seconds must be positive"
        if command.is_expired():
            return False, "command expired"
        if not isinstance(command.parameters, dict):
            return False, "parameters must be a dictionary"
        return True, "ok"

    def serialize(self, command: SwarmCommand) -> str:
        """Serialize command to JSON for transport over tactical links."""
        return json.dumps(command.to_dict(), ensure_ascii=False)

    def deserialize(self, json_str: str) -> SwarmCommand:
        """Deserialize JSON command payload with strict validation."""
        try:
            payload = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid command JSON: {exc}") from exc

        required = {"command_id", "command_type", "target_agents", "parameters", "issued_by", "issued_at"}
        missing = required - set(payload.keys())
        if missing:
            raise ValueError(f"missing command fields: {sorted(missing)}")

        command = SwarmCommand(
            command_id=str(payload["command_id"]),
            command_type=CommandType(str(payload["command_type"])),
            target_agents=list(payload["target_agents"]),
            parameters=dict(payload.get("parameters", {})),
            issued_by=str(payload.get("issued_by", "autonomy")),
            issued_at=datetime.fromisoformat(str(payload["issued_at"])),
            priority=int(payload.get("priority", 3)),
            ttl_seconds=float(payload.get("ttl_seconds", 60.0)),
        )
        valid, reason = self.validate_command(command)
        if not valid:
            raise ValueError(reason)
        return command

    def create_broadcast(self, command_type: CommandType, parameters: dict) -> SwarmCommand:
        """Create command targeting all agents in current swarm."""
        return self.create_command(command_type, ["all"], parameters)

    def create_emergency_stop(self) -> SwarmCommand:
        """Create high-priority emergency stop command for immediate halt."""
        return self.create_command(
            command_type=CommandType.EMERGENCY_STOP,
            target_agents=["all"],
            parameters={"reason": "emergency stop"},
            issued_by="autonomy",
            priority=1,
            ttl=5.0,
        )

    def filter_expired(self, commands: List[SwarmCommand]) -> List[SwarmCommand]:
        """Remove expired commands from tactical command queues."""
        return [command for command in commands if not command.is_expired()]

