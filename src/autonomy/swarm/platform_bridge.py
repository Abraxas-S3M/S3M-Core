"""Bridge platform adapters into swarm-agent coordination contracts.

Military/tactical context:
This bridge keeps platform-level telemetry and command primitives aligned with
the swarm C2 agent model so mission orders stay executable on heterogeneous
ground, air, and maritime assets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    CommandType,
    SwarmCommand,
)
from src.platforms.common import (
    MobilityCommand,
    MobilityCommandType,
    PlatformAdapter,
    PlatformState,
)


@dataclass
class SensorCommand:
    """Lightweight sensor tasking command for adapter-side execution."""

    command: str
    parameters: Dict[str, Any] = field(default_factory=dict)


class SwarmPlatformBridge:
    """Translate between swarm control-plane objects and platform adapters."""

    def __init__(self, adapter: PlatformAdapter, default_role: AgentRole = AgentRole.FOLLOWER) -> None:
        self.adapter = adapter
        self.default_role = default_role
        self.command_history: List[MobilityCommand | SensorCommand] = []

        connected = self.adapter.connect()
        if connected is False:
            raise RuntimeError("failed to connect platform adapter")

        initial_state = self.adapter.read_state()
        self.agent_info = self._create_agent_info(initial_state)

    @staticmethod
    def platform_type_to_capability(platform_type: Any) -> AgentCapability:
        """Map concrete platform domain to swarm tactical capability."""
        name = getattr(platform_type, "name", None)
        value = getattr(platform_type, "value", None)
        normalized = str(name or value or platform_type).strip().lower()
        mapping = {
            "ugv": AgentCapability.GROUND,
            "uav": AgentCapability.AIR,
            "usv": AgentCapability.MARITIME,
            "fixed": AgentCapability.GROUND,
            "fixed_node": AgentCapability.GROUND,
        }
        if normalized not in mapping:
            raise ValueError(f"unsupported platform_type for swarm bridge: {platform_type!r}")
        return mapping[normalized]

    def _create_agent_info(self, state: PlatformState) -> AgentInfo:
        return AgentInfo(
            agent_id=state.platform_id,
            role=self.default_role,
            state=self._platform_state_to_agent_state(state),
            capability=self.platform_type_to_capability(state.platform_type),
            position=self._coerce_position(state.position) or (0.0, 0.0, 0.0),
            heading=0.0,
            speed=0.0,
            battery_pct=100.0,
            fuel_pct=100.0,
            current_mission=None,
            last_heartbeat=datetime.now(timezone.utc),
            sensor_loadout=[],
            weapon_loadout=[],
            comms_status="nominal",
        )

    def translate_swarm_command(self, command: SwarmCommand) -> List[MobilityCommand | SensorCommand]:
        """Translate a high-level swarm command into adapter-level primitives."""
        translated: List[MobilityCommand | SensorCommand] = []

        if command.command_type == CommandType.MOVE_TO:
            target = self._coerce_position(
                command.parameters.get("target_position") or command.parameters.get("position")
            )
            if target is None:
                raise ValueError("MOVE_TO command requires target_position")
            translated.append(MobilityCommand(command_type=MobilityCommandType.MOVE_TO, target_position=target))
        elif command.command_type == CommandType.CHANGE_FORMATION:
            target = self._extract_formation_target(command)
            if target is not None:
                translated.append(
                    MobilityCommand(command_type=MobilityCommandType.MOVE_TO, target_position=target)
                )
        elif command.command_type in {CommandType.HOLD, CommandType.EMERGENCY_STOP}:
            translated.append(MobilityCommand(command_type=MobilityCommandType.HOLD_POSITION))
        elif command.command_type == CommandType.RTB:
            target = self._coerce_position(command.parameters.get("base_position"))
            if target is not None:
                translated.append(MobilityCommand(command_type=MobilityCommandType.MOVE_TO, target_position=target))
            else:
                translated.append(MobilityCommand(command_type=MobilityCommandType.HOLD_POSITION))
        else:
            translated.append(
                SensorCommand(
                    command=command.command_type.value,
                    parameters=dict(command.parameters),
                )
            )

        self.command_history.extend(translated)
        return translated

    def dispatch_swarm_command(self, command: SwarmCommand) -> List[MobilityCommand | SensorCommand]:
        """Translate and dispatch commands when adapter handlers exist."""
        translated = self.translate_swarm_command(command)
        for item in translated:
            if isinstance(item, MobilityCommand):
                if hasattr(self.adapter, "execute_mobility_command"):
                    self.adapter.execute_mobility_command(item)  # type: ignore[attr-defined]
                elif hasattr(self.adapter, "execute_command"):
                    self.adapter.execute_command(item)  # type: ignore[attr-defined]
            else:
                if hasattr(self.adapter, "execute_sensor_command"):
                    self.adapter.execute_sensor_command(item)  # type: ignore[attr-defined]
                elif hasattr(self.adapter, "execute_command"):
                    self.adapter.execute_command(item)  # type: ignore[attr-defined]
        return translated

    def platform_state_to_agent_updates(self, state: PlatformState) -> Dict[str, Any]:
        """Convert platform telemetry into mutable AgentInfo update fields."""
        return {
            "position": self._coerce_position(state.position) or self.agent_info.position,
            "capability": self.platform_type_to_capability(state.platform_type),
            "state": self._platform_state_to_agent_state(state),
            "last_heartbeat": datetime.now(timezone.utc),
        }

    def update_from_platform_state(self, state: Optional[PlatformState] = None) -> AgentInfo:
        """Refresh cached AgentInfo from latest platform state snapshot."""
        current_state = state or self.adapter.read_state()
        updates = self.platform_state_to_agent_updates(current_state)
        for key, value in updates.items():
            setattr(self.agent_info, key, value)
        return self.agent_info

    def _extract_formation_target(self, command: SwarmCommand) -> Optional[Tuple[float, float, float]]:
        target_positions = command.parameters.get("target_positions", {})
        if not isinstance(target_positions, dict):
            return None
        raw_target = target_positions.get(self.agent_info.agent_id)
        return self._coerce_position(raw_target)

    @staticmethod
    def _coerce_position(value: Any) -> Optional[Tuple[float, float, float]]:
        if value is None:
            return None
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError("position-like values must be 3D tuple/list")
        return (float(value[0]), float(value[1]), float(value[2]))

    @staticmethod
    def _platform_state_to_agent_state(state: PlatformState) -> AgentState:
        health_state = str(getattr(getattr(state, "health_state", None), "value", "")).strip().lower()
        autonomy_mode = str(getattr(getattr(state, "autonomy_mode", None), "value", "")).strip().lower()
        if health_state == "fault":
            return AgentState.MAINTENANCE
        if autonomy_mode == "manual":
            return AgentState.IDLE
        return AgentState.ACTIVE

